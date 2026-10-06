"""Safety Council emergency pause (D-09): pause-only, short, non-stacking, must be ratified.

A pause freezes tranche release for ONE project. It can never cancel, spend, amend or move
funds, expires by height with no further action, and cannot be renewed by the council alone:
extension needs a ratifying vote. After an unratified pause lapses the same project cannot be
re-paused by the council for `pause_max` heights, so a captured council cannot chain pauses.
"""
from __future__ import annotations

from .params import Params
from .roles import Actor, RoleRegistry
from .treasury import RuleViolation, Treasury


class Emergency:
    def __init__(self, p: Params, registry: RoleRegistry, treasury: Treasury):
        self.p, self.reg, self.tr = p, registry, treasury
        self.history: dict[str, list] = {}      # project -> [(start, end, ratified)]

    def _last(self, project: str):
        h = self.history.get(project)
        return h[-1] if h else None

    def pause(self, agent: str, project: str, height: int, duration: int, reason: str) -> int:
        ok, why = self.reg.can(agent, "PAUSE", height)
        if not ok:
            raise RuleViolation(f"not authorized to pause: {why}")
        if project not in self.tr.escrow or project in self.tr.terminated:
            raise RuleViolation("nothing to pause")
        if type(height) is not int or height < 0:
            raise RuleViolation("invalid height")
        if not isinstance(reason,str) or not 0 < len(reason) <= 1024:
            raise RuleViolation("a public reason code is required")
        if type(duration) is not int or not 0 < duration <= self.p.pause_max:
            raise RuleViolation("duration outside (0, pause_max]")
        last = self._last(project)
        if last and height < last[1]:
            raise RuleViolation("already paused")
        if last and not last[2] and height < last[1] + self.p.pause_max:
            raise RuleViolation("re-pause cooldown: needs a ratifying vote")
        funded = [a for a,amount in self.tr.escrow.items() if amount > 0 and a not in self.tr.terminated]
        concurrent = sum(height < self.tr.paused_until.get(a,0) for a in funded)
        cap = max(1,(len(funded)*self.p.pause_concurrent_bps+9999)//10000)
        if concurrent >= cap:
            raise RuleViolation("concurrent pause circuit breaker; use public governance")
        event = self.reg._guard_check(Actor.agent(agent),height,"pause")
        self.reg._guard_commit(event)
        end = height + duration
        self.tr.paused_until[project] = end
        self.history.setdefault(project, []).append((height, end, False))
        self.reg._log(height, Actor.agent(agent), "PAUSE", project, reason)
        return end

    def ratify(self, actor: Actor, project: str, height: int, extend_to: int) -> None:
        """A passed vote extends a live pause to `extend_to` (e.g. through a corrective vote)."""
        if type(height) is not int or height < 0 or type(extend_to) is not int:
            raise RuleViolation("invalid ratification heights")
        last = self._last(project)
        if not last or not last[0] <= height < last[1]:
            raise RuleViolation("no live pause to ratify")
        if extend_to <= last[1]:
            raise RuleViolation("ratification must extend the pause")
        self.reg._authorize(actor, {"VOTE"}, height, "PAUSE_RATIFY", project)
        self.reg._spend(actor)
        self.tr.paused_until[project] = extend_to
        self.history[project][-1] = (last[0], extend_to, True)
        self.reg._log(height, actor, "PAUSE_RATIFIED", project, str(extend_to))

    def is_paused(self, project: str, height: int) -> bool:
        return height < self.tr.paused_until.get(project, 0)
