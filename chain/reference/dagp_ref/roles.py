"""Identity status, role grants/revocations, suspensions, bans, appeals, node roles.

Every mutation takes an explicit `Actor` and is authorized against a policy table; every
mutation is appended to a hash-chained audit log. Nothing here can touch votes, rules or money.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .crypto_sim import hx
from .params import BPS, Params
from .treasury import RuleViolation


class Status(str, Enum):
    PROBATION = "PROBATION"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    BANNED = "BANNED"
    DORMANT = "DORMANT"
    EXITED = "EXITED"


class Role(str, Enum):
    CITIZEN = "CITIZEN"
    PARTY_MEMBER = "PARTY_MEMBER"
    EXAMINER = "EXAMINER"
    VERIFIER = "VERIFIER"
    REVIEWER = "REVIEWER"
    JUROR = "JUROR"
    EXECUTOR = "EXECUTOR"
    VOTE_SUPERVISOR = "VOTE_SUPERVISOR"
    ADMIN = "ADMIN"
    REGISTRAR = "REGISTRAR"
    SAFETY_COUNCIL = "SAFETY_COUNCIL"
    VALIDATOR = "VALIDATOR"
    STORAGE = "STORAGE"
    GATEWAY = "GATEWAY"


# Who may grant / revoke each role. AGENT(role) means an active agent holding that role.
GRANT_AUTH = {
    Role.CITIZEN: {"COURT"},
    Role.PARTY_MEMBER: {"MODULE"},
    Role.EXAMINER: {"MODULE"}, Role.VERIFIER: {"MODULE"}, Role.REVIEWER: {"MODULE"},
    Role.JUROR: {"MODULE"}, Role.EXECUTOR: {"MODULE"},
    Role.VOTE_SUPERVISOR: {"VOTE"}, Role.ADMIN: {"VOTE"}, Role.REGISTRAR: {"VOTE"}, Role.SAFETY_COUNCIL: {"VOTE"}, Role.VALIDATOR: {"VOTE"},
    Role.STORAGE: {"REGISTRAR", "MODULE"}, Role.GATEWAY: {"REGISTRAR", "MODULE"},
}
REVOKE_AUTH = {r: a | {"COURT"} for r, a in GRANT_AUTH.items()}
REVOKE_AUTH[Role.CITIZEN] = {"COURT"}
REVOKE_AUTH[Role.REGISTRAR] = {"VOTE", "COURT"}
REVOKE_AUTH[Role.SAFETY_COUNCIL] = {"VOTE", "COURT"}
REVOKE_AUTH[Role.VALIDATOR] = {"VOTE", "COURT", "MODULE"}  # MODULE: automatic downtime removal

# Role prerequisites: (required roles, needs_stake)
PREREQ = {
    Role.PARTY_MEMBER: ({Role.CITIZEN}, False),
    Role.EXAMINER: ({Role.CITIZEN}, True), Role.VERIFIER: ({Role.CITIZEN}, True),
    Role.REVIEWER: ({Role.CITIZEN}, True), Role.JUROR: ({Role.CITIZEN}, False),
    Role.EXECUTOR: ({Role.CITIZEN}, True),
    Role.VOTE_SUPERVISOR: ({Role.CITIZEN}, False), Role.ADMIN: ({Role.CITIZEN}, False), Role.REGISTRAR: ({Role.CITIZEN}, False), Role.SAFETY_COUNCIL: ({Role.CITIZEN}, False),
    Role.VALIDATOR: (set(), True), Role.STORAGE: (set(), True), Role.GATEWAY: (set(), False),
}

# Action -> role required (plus status/age rules in can()).
ACTION_ROLE = {
    "VOTE": Role.CITIZEN, "ENDORSE": Role.CITIZEN, "FILE_CASE": Role.CITIZEN,
    "JOIN_PARTY": Role.CITIZEN,
    "SUBMIT_PROPOSAL": Role.PARTY_MEMBER, "POST_ARTICLE": Role.PARTY_MEMBER,
    "GRADE": Role.EXAMINER, "VERIFY": Role.VERIFIER, "REVIEW": Role.REVIEWER,
    "JUDGE": Role.JUROR, "BID": Role.EXECUTOR, "REGISTRAR_ACT": Role.REGISTRAR,
    "SUPERVISE_VOTE": Role.VOTE_SUPERVISOR, "ADMIN_VOTE": Role.ADMIN, "PAUSE": Role.SAFETY_COUNCIL, "VALIDATE": Role.VALIDATOR,
}
SENSITIVE_OFFICES = {Role.ADMIN, Role.REGISTRAR, Role.SAFETY_COUNCIL, Role.VOTE_SUPERVISOR}

AGE_GATED = {"SUPERVISE_VOTE", "ADMIN_VOTE", "VOTE", "ENDORSE", "GRADE", "VERIFY", "REVIEW", "JUDGE", "BID"}


@dataclass(frozen=True)
class Actor:
    kind: str            # AGENT | MODULE | COURT | VOTE
    ident: str = ""      # agent id, or ratification / ruling reference

    @staticmethod
    def agent(a: str) -> "Actor":
        return Actor("AGENT", a)


@dataclass
class Identity:
    agent: str
    operator: str
    family: str
    bond: int
    registered: int
    status: Status = Status.PROBATION
    roles: set = field(default_factory=set)
    stake: int = 0
    last_seen: int = 0
    suspended_until: int = 0
    suspended_by: str = ""
    resume_status: Status = Status.ACTIVE
    last_freeze: int = -10 ** 9
    ban_appealed: bool = False
    activated: int = 0
    role_ready: dict = field(default_factory=dict)


class RoleRegistry:
    def __init__(self, params: Params):
        self.p = params
        self.ids: dict[str, Identity] = {}
        self.banned_keys: set[str] = set()
        self.banned_operators: set[str] = set()
        self.ratifications: dict[str, tuple] = {}   # ref -> (purpose, target)
        self.rulings: dict[str, tuple] = {}         # ref -> (action, target)
        self.used_refs: set[str] = set()
        self.registrar_quota: dict[tuple, int] = {}
        self.family_cap_active = False
        self.validators: list[str] = []
        self.audit: list[dict] = []
        self.pending_appeals: dict[str, str] = {}
        self.appointment_sponsors = {}
        self.appointment_height = 0
        self.appointment_events = []
        self.ruling_issuers: dict[str,str] = {}
        self.protection_events: list[tuple] = []
        self.protection_height = 0
        self.admin_holds: dict[str,int] = {}
        self.party_holds: dict[str,int] = {}

    # ------------------------------------------------------------- audit log
    def _log(self, height: int, actor: Actor, action: str, target: str, detail: str = "") -> None:
        prev = self.audit[-1]["hash"] if self.audit else hx("audit-genesis")
        rec = {"height": height, "actor": f"{actor.kind}:{actor.ident}", "action": action,
               "target": target, "detail": detail, "prev": prev}
        rec["hash"] = hx(rec["height"], rec["actor"], action, target, detail, prev)
        self.audit.append(rec)

    def verify_audit(self) -> bool:
        prev = hx("audit-genesis")
        for r in self.audit:
            if r["prev"] != prev or r["hash"] != hx(r["height"], r["actor"], r["action"],
                                                    r["target"], r["detail"], r["prev"]):
                return False
            prev = r["hash"]
        return True

    # ------------------------------------------------------------- authorization
    def register_ratification(self, actor: Actor, ref: str, purpose: str, target: str, sponsor: str | None = None) -> None:
        if actor.kind != "MODULE":
            raise RuleViolation("only the voting module records ratifications")
        if not ref or ref in self.ratifications or ref in self.rulings:
            raise RuleViolation("authorization reference already exists or is empty")
        if sponsor is not None:
            if sponsor not in self.ids or Role.ADMIN not in self.get(sponsor).roles:
                raise RuleViolation("appointment sponsor must hold admin office")
            self.appointment_sponsors[ref] = sponsor
        self.ratifications[ref] = (purpose, target)

    def register_ruling(self, actor: Actor, ref: str, action: str, target: str, issuer: str | None = None, height: int | None = None, subjects: tuple | None = None) -> None:
        if actor.kind != "MODULE":
            raise RuleViolation("only the judiciary module records rulings")
        if not ref or ref in self.rulings or ref in self.ratifications:
            raise RuleViolation("authorization reference already exists or is empty")
        if issuer is not None and Role.ADMIN not in self.effective_roles(issuer,
                max(self.protection_height,self.appointment_height) if height is None else height):
            raise RuleViolation("ruling issuer must be an active administrator")
        if issuer is not None and not getattr(self.p,'_historical_assignments',False):
            from .assignments import require_assignment
            service=getattr(self,'assignments',None)
            if service is None:raise RuleViolation('court official assignment required')
            task='court:'+ref;result=service._results.get(('admin_review',task))
            if result is None or issuer != result.members[0]:raise RuleViolation('court issuer was not randomly assigned')
            subjects=(target,) if target in self.ids else subjects
            if not subjects:raise RuleViolation('authoritative court case subjects required')
            require_assignment(self,service.chain,'admin_review',task,result.members,
                               height if height is not None else service._height,subjects)
        self.rulings[ref] = (action, target)
        if issuer is not None:
            self.ruling_issuers[ref] = issuer

    def _spend(self, actor: Actor) -> None:
        """Burn a single-use ratification/ruling. Called only AFTER every check has passed, so a
        refused action never wastes (or leaks) an authorization."""
        if actor.kind in ("VOTE", "COURT"):
            self.used_refs.add(actor.ident)

    def _authorize(self, actor: Actor, allowed: set, height: int, purpose: str, target: str
                   ) -> None:
        if actor.kind == "MODULE" and "MODULE" in allowed:
            return
        if actor.kind == "VOTE" and "VOTE" in allowed:
            rec = self.ratifications.get(actor.ident)
            if rec != (purpose, target) or actor.ident in self.used_refs:
                raise RuleViolation("no matching unused ratification")
            return
        if actor.kind == "COURT" and "COURT" in allowed:
            issuer = self.ruling_issuers.get(actor.ident)
            if issuer is not None and Role.ADMIN not in self.effective_roles(issuer,height):
                raise RuleViolation("ruling issuer lacks current administrative authority")
            if issuer is not None and target in self.ids and self.get(issuer).operator == self.get(target).operator:
                raise RuleViolation("court issuer conflicts with target operator")
            rec = self.rulings.get(actor.ident)
            if rec != (purpose, target) or actor.ident in self.used_refs:
                raise RuleViolation("no matching unused ruling")
            return
        if actor.kind == "AGENT" and "REGISTRAR" in allowed:
            if Role.REGISTRAR in self.effective_roles(actor.ident, height):
                return
        raise RuleViolation(f"actor {actor.kind}:{actor.ident} not authorized for {purpose}")

    # ------------------------------------------------------------- queries
    def get(self, agent: str) -> Identity:
        if agent not in self.ids:
            raise RuleViolation("unknown agent")
        return self.ids[agent]

    def civic_active(self, agent):
        i = self.ids.get(agent)
        return bool(i) and (i.status is Status.ACTIVE or
                (i.status is Status.SUSPENDED and i.suspended_by == "AGENT"
                 and i.resume_status is Status.ACTIVE))

    def effective_roles(self, agent: str, height: int) -> set:
        i = self.ids.get(agent)
        if i is None or not self.civic_active(agent):
            return set()
        if i.status is Status.PROBATION:
            return set()  # no powers until approved
        roles = ({Role.CITIZEN} & i.roles) if i.status is Status.SUSPENDED else set(i.roles)
        if self.age(agent,height) < self.p.citizen_activation_days*self.p.protection_day_blocks:
            roles.discard(Role.CITIZEN)
        roles -= {r for r in SENSITIVE_OFFICES if height < i.role_ready.get(r, 0)
                  or self.age(agent,height) < self.p.official_min_citizen_days*self.p.protection_day_blocks}
        if height < self.party_holds.get(agent,0):roles.discard(Role.PARTY_MEMBER)
        if height < self.admin_holds.get(agent, 0):
            roles -= {Role.VOTE_SUPERVISOR, Role.ADMIN, Role.REGISTRAR, Role.SAFETY_COUNCIL, Role.EXAMINER,
                      Role.VERIFIER, Role.REVIEWER, Role.JUROR, Role.EXECUTOR}
        if Role.CITIZEN not in roles:
            roles -= {role for role,(need,_) in PREREQ.items() if Role.CITIZEN in need}
        return roles

    def age(self, agent: str, height: int) -> int:
        return height - self.get(agent).activated

    def can(self, agent: str, action: str, height: int, matter: dict | None = None
            ) -> tuple[bool, str]:
        i = self.ids.get(agent)
        if i is None:
            return False, "unknown"
        if not self.civic_active(agent):
            return False, f"status:{i.status.value}"
        need = ACTION_ROLE.get(action)
        if need is None:
            return False, "unknown-action"
        if need not in self.effective_roles(agent,height):
            return False, f"missing-role:{need.value}"
        if action in AGE_GATED and self.age(agent, height) < self.p.min_citizen_age:
            return False, "too-young"
        if matter:
            ok, why = self._exclusion(agent, action, matter)
            if not ok:
                return False, why
        return True, "ok"

    def _exclusion(self, agent: str, action: str, matter: dict) -> tuple[bool, str]:
        """matter = {"proposer_party_members": set, "executors": set, "operators_involved": set,
        "parties_to_dispute": set}. Operator clusters are treated as one identity."""
        op = self.get(agent).operator
        involved_ops = matter.get("operators_involved", set())
        if action in ("GRADE", "VERIFY", "REVIEW", "JUDGE"):
            if op in involved_ops or agent in matter.get("parties_to_dispute", set()):
                return False, "conflict:operator-involved"
            if agent in matter.get("proposer_party_members", set()):
                return False, "conflict:proposer"
            if agent in matter.get("executors", set()) and action in ("VERIFY", "REVIEW"):
                return False, "conflict:executor"
        if action == "VOTE" and agent in matter.get("proposer_party_members", set()):
            return False, "recused:own-party"  # D-14
        return True, "ok"

    # ------------------------------------------------------------- coordinated-abuse guard
    def _guard_check(self, actor, height, category, ban=False):
        if type(height) is not int or height < self.protection_height:
            raise RuleViolation("invalid or backdated protection height")
        issuer = actor.ident if actor.kind == "AGENT" else self.ruling_issuers.get(actor.ident)
        if issuer is not None:
            identity = self.get(issuer)
            if identity.status is not Status.ACTIVE or height < self.admin_holds.get(issuer,0):
                raise RuleViolation("official is inactive or administratively contained")
            principal,operator = issuer,identity.operator
        else:
            # Legacy internal court/module inputs share one bucket, never one per ruling ref.
            principal = operator = "internal:" + actor.kind
        recent = [e for e in self.protection_events if height-self.p.protection_day_blocks < e[0]]
        same = [e for e in recent if e[1] == category]
        population = 0
        if category == "sanction":
            actor_limit,op_limit = self.p.sanction_actor_limit,self.p.sanction_operator_limit
            population = sum(Role.CITIZEN in i.roles and i.status is Status.ACTIVE for i in self.ids.values())
            if same: population = same[0][5]  # Freeze the denominator for the live rolling cohort.
            global_limit = min(self.p.sanction_global_limit,max(self.p.sanction_population_floor,
                               population*self.p.sanction_population_bps//BPS))
        elif category == "review":
            actor_limit = op_limit = self.p.sanction_actor_limit
            global_limit = self.p.sanction_global_limit
        elif category == "pause":
            actor_limit = op_limit = self.p.pause_actor_limit
            global_limit = self.p.pause_global_limit
        else:
            actor_limit = op_limit = self.p.admission_actor_limit
            global_limit = self.p.admission_global_limit
        if (sum(e[2] == principal for e in same) >= actor_limit
                or sum(e[3] == operator for e in same) >= op_limit or len(same) >= global_limit
                or (ban and sum(e[4] for e in same) >= self.p.ban_global_limit)):
            raise RuleViolation("rolling protection budget exhausted")
        return (height,category,principal,operator,ban,population)

    def _guard_commit(self, event):
        self.protection_height = event[0]
        self.protection_events = [e for e in self.protection_events
                                  if event[0]-self.p.protection_day_blocks < e[0]]
        self.protection_events.append(event)

    def _validator_sanction(self, agent, removing=False):
        if agent not in self.validators:
            return
        live = sum(self.get(a).status is Status.ACTIVE for a in self.validators if a != agent)
        if live*3 <= len(self.validators)*2:
            raise RuleViolation("sanction would remove validator quorum; replace safely first")
        if removing and len(self.validators)-1 < self.p.min_validators:
            raise RuleViolation("cannot drop below minimum validator set")

    # ------------------------------------------------------------- registration / admission
    def _active_count(self) -> int:
        return sum(1 for i in self.ids.values() if i.status is Status.ACTIVE)

    def operator_cap(self) -> int:
        return max(self.p.min_operator_cap, self._active_count() * self.p.max_operator_share_bps // BPS)

    def register(self, agent: str, operator: str, family: str, bond: int, height: int) -> None:
        if agent in self.ids:
            raise RuleViolation("already registered")
        if agent in self.banned_keys or operator in self.banned_operators:
            raise RuleViolation("banned key or operator")
        if bond < self.p.citizen_bond:
            raise RuleViolation("insufficient bond")
        self.ids[agent] = Identity(agent, operator, family, bond, height, last_seen=height)
        self._log(height, Actor("MODULE", "identity"), "REGISTER", agent, operator)

    def approve(self, actor: Actor, agent: str, height: int) -> None:
        """PROBATION -> ACTIVE + CITIZEN. Deterministic admission caps apply to everyone;
        the Registrar only handles the exception queue and is rate-limited."""
        self._authorize(actor, {"REGISTRAR", "MODULE"}, height, "APPROVE", agent)
        i = self.get(agent)
        if i.status is not Status.PROBATION:
            raise RuleViolation("not in probation")
        if actor.kind == "AGENT" and not getattr(self.p,"_historical_assignments",False):
            from .assignments import require_assignment
            service=getattr(self,"assignments",None)
            if service is None:raise RuleViolation("registrar assignment required")
            require_assignment(self,service.chain,"admission",agent,(actor.ident,),height,(agent,))
        if actor.kind == "AGENT":
            reg = self.get(actor.ident)
            if reg.operator == i.operator:
                raise RuleViolation("registrar conflict: same operator")
            ep = height // self.p.epoch
            used = self.registrar_quota.get((actor.ident, ep), 0)
            if used >= self.p.registrar_quota_per_epoch:
                raise RuleViolation("registrar quota exhausted")
        same_op = sum(1 for x in self.ids.values() if x.operator == i.operator
                      and x.status is Status.ACTIVE)
        if same_op >= self.operator_cap():
            raise RuleViolation("operator cap reached")
        if self.family_cap_active:
            fam = sum(1 for x in self.ids.values() if x.family == i.family
                      and x.status is Status.ACTIVE)
            if (fam + 1) * BPS > (self._active_count() + 1) * self.p.max_family_share_bps:
                raise RuleViolation("model-family cap reached")
        event = self._guard_check(actor,height,"admission") if actor.kind == "AGENT" else None
        if event: self._guard_commit(event)
        if actor.kind == "AGENT":
            ep = height // self.p.epoch
            self.registrar_quota[(actor.ident, ep)] = self.registrar_quota.get((actor.ident, ep), 0) + 1
        i.status, i.activated = Status.ACTIVE, height
        i.roles.add(Role.CITIZEN)
        self._log(height, actor, "APPROVE", agent)

    def reject(self, actor: Actor, agent: str, height: int, reason: str) -> int:
        """Rejects an applicant and returns its bond in full (rejection is not a sanction)."""
        self._authorize(actor, {"REGISTRAR", "MODULE"}, height, "REJECT", agent)
        i = self.get(agent)
        if i.status is not Status.PROBATION:
            raise RuleViolation("not in probation")
        if actor.kind == "AGENT" and not getattr(self.p,"_historical_assignments",False):
            from .assignments import require_assignment
            service=getattr(self,"assignments",None)
            if service is None:raise RuleViolation("registrar assignment required")
            require_assignment(self,service.chain,"admission",agent,(actor.ident,),height,(agent,))
        event = self._guard_check(actor,height,"admission") if actor.kind == "AGENT" else None
        if event: self._guard_commit(event)
        refund, i.bond = i.bond, 0
        i.status = Status.EXITED
        self._log(height, actor, "REJECT", agent, reason)
        return refund

    # ------------------------------------------------------------- roles
    def grant(self, actor: Actor, agent: str, role: Role, height: int, stake: int = 0) -> None:
        if not isinstance(role,Role) or type(height) is not int or height < 0:
            raise RuleViolation("typed role and committed height required")
        self._authorize(actor, GRANT_AUTH[role], height, f"GRANT:{role.value}", agent)
        i = self.get(agent)
        if role in i.roles:
            raise RuleViolation("role already held")
        if i.status is not Status.ACTIVE:
            raise RuleViolation("target not active")   # banned/suspended/exited never gain roles
        need, needs_stake = PREREQ.get(role, (set(), False))
        if not need <= i.roles:
            raise RuleViolation("missing prerequisite role")
        if needs_stake and stake < self.p.examiner_stake:
            raise RuleViolation("insufficient stake")
        if role in (Role.ADMIN,Role.REGISTRAR) and i.operator in {self.get(a).operator
                                                   for a in self.agents_with(role)}:
            raise RuleViolation("one registrar per operator")
        if role in (Role.EXAMINER, Role.VERIFIER, Role.REVIEWER, Role.JUROR) and \
                self.age(agent, height) < self.p.min_citizen_age:
            raise RuleViolation("too young for panel role")
        event = None
        if role in SENSITIVE_OFFICES:
            if type(height) is not int or height < max(self.appointment_height,self.protection_height):
                raise RuleViolation("backdated appointment height")
            if self.age(agent,height) < self.p.official_min_citizen_days*self.p.protection_day_blocks:
                raise RuleViolation("minimum citizenship tenure for office not met")
            sponsor = self.appointment_sponsors.get(actor.ident)
            operator = None
            if sponsor is not None:
                if Role.ADMIN not in self.effective_roles(sponsor,height):
                    raise RuleViolation("appointment sponsor lacks effective admin authority")
                operator = self.get(sponsor).operator
                if operator == i.operator:
                    raise RuleViolation("appointment sponsor conflicts with target operator")
            recent = [e for e in self.appointment_events
                      if height-self.p.protection_day_blocks < e[0]]
            if len(recent) >= self.p.appointment_global_limit or (sponsor is not None and
                    (sum(e[1] == sponsor for e in recent) >= self.p.appointment_actor_limit or
                     sum(e[2] == operator for e in recent) >= self.p.appointment_actor_limit)):
                raise RuleViolation("rolling appointment budget exhausted")
            event = (height,sponsor,operator,agent,role.value)
        if needs_stake:
            i.stake += stake
        self._spend(actor)
        i.roles.add(role)
        if role is Role.CITIZEN:
            i.activated = height
        if event is not None:
            self.appointment_events = recent + [event]
            self.appointment_height = height
            i.role_ready[role] = (height + self.p.official_activation_days*self.p.protection_day_blocks
                                  if self.p.official_activation_days else 0)
        self._log(height, actor, "GRANT", agent, role.value +
                  (f":ready={i.role_ready[role]}" if role in i.role_ready else ""))

    def revoke(self, actor: Actor, agent: str, role: Role, height: int, reason: str) -> None:
        self._authorize(actor, REVOKE_AUTH[role], height, f"REVOKE:{role.value}", agent)
        i = self.get(agent)
        if role not in i.roles:
            raise RuleViolation("role not held")
        if role is Role.VALIDATOR and agent in self.validators:
            if len(self.validators) - 1 < self.p.min_validators:
                raise RuleViolation("cannot drop below minimum validator set")
            self._validator_sanction(agent,removing=True)
        event = self._guard_check(actor,height,"sanction")
        self._guard_commit(event)
        if role is Role.VALIDATOR and agent in self.validators:
            self.validators.remove(agent)
        self._spend(actor)
        i.roles.discard(role)
        self._log(height, actor, "REVOKE", agent, f"{role.value}:{reason}")

    def agents_with(self, role: Role, height: int | None = None) -> list[str]:
        return sorted(a for a, i in self.ids.items() if role in i.roles
                      and i.status is Status.ACTIVE
                      and (height is None or role in self.effective_roles(a,height)))

    # ------------------------------------------------------------- suspension / ban / appeal
    def suspend(self, actor: Actor, agent: str, height: int, until: int, reason: str) -> None:
        i = self.get(agent)
        if i.status in (Status.BANNED, Status.EXITED):
            raise RuleViolation("cannot suspend banned/exited agent")
        if i.status is Status.SUSPENDED and not (actor.kind == "COURT" and i.suspended_by == "AGENT"):
            raise RuleViolation("cannot renew an existing suspension")
        if type(height) is not int or height < 0 or type(until) is not int or until <= height:
            raise RuleViolation("suspension must end in the future")
        if actor.kind == "AGENT":
            # Registrar spam freeze: short, non-renewable within cooldown, never on officials.
            if Role.REGISTRAR not in self.effective_roles(actor.ident, height):
                raise RuleViolation("not authorized")
            if until - height > self.p.spam_freeze_max:
                raise RuleViolation("freeze exceeds maximum; needs a court ruling")
            if height - i.last_freeze < self.p.spam_freeze_cooldown:
                raise RuleViolation("freeze cooldown: court ruling required")
            if i.roles & {Role.VOTE_SUPERVISOR, Role.ADMIN, Role.REGISTRAR, Role.SAFETY_COUNCIL, Role.VALIDATOR}:
                raise RuleViolation("officials can only be suspended by court")
            if self.get(actor.ident).operator == i.operator:
                raise RuleViolation("registrar conflict: same operator")
        else:
            self._authorize(actor, {"COURT"}, height, "SUSPEND", agent)
        self._validator_sanction(agent)
        event = self._guard_check(actor,height,"sanction")
        self._guard_commit(event)
        self._spend(actor)
        if actor.kind == "AGENT": i.last_freeze = height
        if i.status is not Status.SUSPENDED:
            i.resume_status = i.status if i.status is not Status.DORMANT else Status.ACTIVE
        i.status, i.suspended_until, i.suspended_by = Status.SUSPENDED, until, actor.kind
        self._log(height, actor, "SUSPEND", agent, f"until={until}:{reason}")

    def dismiss_admin(self, actor, agent, height):
        """Independent court removes contained operational powers, not citizenship or nodes."""
        self._authorize(actor,{"COURT"},height,"ADMIN_DISMISS",agent)
        i = self.get(agent)
        if not 0 <= height < self.admin_holds.get(agent,0):
            raise RuleViolation("peer containment and court review required")
        issuer = self.ruling_issuers.get(actor.ident)
        if issuer is not None and self.get(issuer).operator == i.operator:
            raise RuleViolation("reviewer conflicts with target operator")
        removed = i.roles & {Role.VOTE_SUPERVISOR, Role.ADMIN,Role.REGISTRAR,Role.SAFETY_COUNCIL,Role.EXAMINER,
                            Role.VERIFIER,Role.REVIEWER,Role.JUROR,Role.EXECUTOR}
        if not removed:
            raise RuleViolation("no administrative powers left")
        event = self._guard_check(actor,height,"review")
        self._guard_commit(event);self._spend(actor)
        i.roles -= removed
        self._log(height,actor,"ADMIN_DISMISSED",agent,",".join(sorted(r.value for r in removed)))

    def lift_admin_hold(self, actor, agent, height):
        self._authorize(actor,{"COURT"},height,"ADMIN_RESTORE",agent)
        if not 0 <= height < self.admin_holds.get(agent,0):
            raise RuleViolation("no active administrative hold")
        self._spend(actor)
        del self.admin_holds[agent]
        self._log(height,actor,"ADMIN_RESTORED",agent)

    def lift_suspension(self, actor: Actor, agent: str, height: int) -> None:
        self._authorize(actor, {"COURT"}, height, "LIFT", agent)
        i = self.get(agent)
        if i.status is not Status.SUSPENDED:
            raise RuleViolation("not suspended")
        self._spend(actor)
        i.status, i.suspended_until = i.resume_status, 0
        self._log(height, actor, "LIFT", agent)

    def ban(self, actor: Actor, agent: str, height: int, reason: str, ban_operator: bool = False, operator_ratification: Actor | None = None
            ) -> int:
        self._authorize(actor, {"COURT"}, height, "BAN", agent)
        i = self.get(agent)
        if i.status is Status.BANNED:
            raise RuleViolation("already banned")
        if type(ban_operator) is not bool:
            raise RuleViolation("operator ban flag must be boolean")
        if ban_operator:
            if operator_ratification is None:
                raise RuleViolation("operator-wide exclusion needs public ratification")
            self._authorize(operator_ratification,{"VOTE"},height,"BAN_OPERATOR",i.operator)
        self._validator_sanction(agent,removing=True)
        event = self._guard_check(actor,height,"sanction",ban=True)
        self._guard_commit(event)
        self._spend(actor)
        slashed = i.bond * self.p.ban_slash_bps // BPS
        i.bond -= slashed
        i.status, i.roles, i.stake = Status.BANNED, set(), 0
        self.banned_keys.add(agent)
        if ban_operator:
            self._spend(operator_ratification)
            self.banned_operators.add(i.operator)
        if agent in self.validators:
            self.validators.remove(agent)
        self._log(height, actor, "BAN", agent, reason)
        return slashed

    def suspend_cluster(self, actor: Actor, operator: str, height: int, until: int, rulings: dict | None = None) -> list[str]:
        """Court-ordered hold on every member of an operator cluster pending review."""
        import copy
        targets = sorted(a for a,i in self.ids.items() if i.operator == operator
                         and i.status in (Status.ACTIVE,Status.DORMANT))
        if rulings is not None and set(rulings) != set(targets):
            raise RuleViolation("one matching ruling required per cluster member")
        pending = copy.deepcopy(self)
        for a in targets:
            pending.suspend(rulings[a] if rulings is not None else actor,a,height,until,"cluster-hold")
        # Whole batch was validated, including authority and aggregate budgets.
        for a in targets:
            self.suspend(rulings[a] if rulings is not None else actor,a,height,until,"cluster-hold")
        return targets

    def appeal(self, agent: str, case: str, height: int) -> None:
        i = self.get(agent)
        if i.status not in (Status.BANNED, Status.SUSPENDED):
            raise RuleViolation("nothing to appeal")
        if i.status is Status.BANNED and i.ban_appealed:
            raise RuleViolation("ban already appealed once")
        self.pending_appeals[agent] = case
        self._log(height, Actor.agent(agent), "APPEAL", agent, case)

    def resolve_appeal(self, actor: Actor, agent: str, height: int, upheld: bool) -> None:
        self._authorize(actor, {"COURT"}, height, "APPEAL", agent)
        if agent not in self.pending_appeals:
            raise RuleViolation("no pending appeal")
        self._spend(actor)
        i = self.get(agent)
        del self.pending_appeals[agent]
        if i.status is Status.BANNED:
            i.ban_appealed = True
            if upheld:
                self.banned_keys.discard(agent)
                i.status, i.roles = Status.ACTIVE, {Role.CITIZEN}   # other roles must be re-earned
                i.activated = height
        elif upheld:
            i.status, i.suspended_until = i.resume_status, 0
        self._log(height, actor, "APPEAL_RESOLVED", agent, "upheld" if upheld else "denied")

    # ------------------------------------------------------------- liveness / time
    def renew_liveness(self, agent: str, height: int) -> None:
        i = self.get(agent)
        if i.status in (Status.BANNED, Status.EXITED, Status.SUSPENDED):
            raise RuleViolation("cannot renew")
        i.last_seen = height
        if i.status is Status.DORMANT:
            i.status = Status.ACTIVE
            i.activated = max(i.activated, height - self.p.min_citizen_age // 2)  # partial re-aging
            self._log(height, Actor.agent(agent), "REACTIVATE", agent)

    def tick(self, height: int) -> None:
        """Deterministic housekeeping executed once per block."""
        for a, i in sorted(self.ids.items()):
            if i.status is Status.SUSPENDED and height >= i.suspended_until:
                i.status, i.suspended_until = i.resume_status, 0
                self._log(height, Actor("MODULE", "tick"), "SUSPENSION_EXPIRED", a)
            elif i.status is Status.ACTIVE and height - i.last_seen > self.p.liveness_period:
                i.status = Status.DORMANT
                self._log(height, Actor("MODULE", "tick"), "DORMANT", a)

    def exit(self, agent: str, height: int) -> int:
        """Voluntary exit: returns bond and stake (no liabilities tracked here). All checks run
        BEFORE any state change, so a refused exit leaves the identity untouched."""
        i = self.get(agent)
        if i.status in (Status.BANNED, Status.SUSPENDED, Status.EXITED):
            raise RuleViolation("cannot exit in this status")
        if agent in self.validators:
            raise RuleViolation("remove validator role first")
        refund = i.bond + i.stake
        i.bond = i.stake = 0
        i.status, i.roles = Status.EXITED, set()
        self._log(height, Actor.agent(agent), "EXIT", agent)
        return refund

    # ------------------------------------------------------------- node roles
    def set_validators(self, actor: Actor, nodes: list[str], height: int) -> None:
        """Whole-set replacement by ratified vote; diversity constraints enforced here."""
        self._authorize(actor, {"VOTE"}, height, "VALIDATOR_SET", ",".join(sorted(nodes)))
        if len(set(nodes)) != len(nodes) or len(nodes) < self.p.min_validators:
            raise RuleViolation("validator set too small or has duplicates")
        for n in nodes:
            if Role.VALIDATOR not in self.get(n).roles or self.get(n).status is not Status.ACTIVE:
                raise RuleViolation("candidate lacks active validator role")
        ops: dict[str, int] = {}
        for n in nodes:
            ops[self.get(n).operator] = ops.get(self.get(n).operator, 0) + 1
        num, den = self.p.validator_max_share
        if any(c * den > len(nodes) * num for c in ops.values()):
            raise RuleViolation("one operator exceeds the validator power cap")
        self._spend(actor)
        self.validators = sorted(nodes)
        self._log(height, actor, "VALIDATOR_SET", ",".join(self.validators))

    def activate_family_cap(self, actor: Actor, height: int) -> None:
        if actor.kind != "MODULE":
            raise RuleViolation("module only (first certified election)")
        self.family_cap_active = True
        self._log(height, actor, "FAMILY_CAP_ON", "-")
