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
        if not reason:
            raise RuleViolation("a public reason code is required")
        if not 0 < duration <= self.p.pause_max:
            raise RuleViolation("duration outside (0, pause_max]")
        last = self._last(project)
        if last and height < last[1]:
            raise RuleViolation("already paused")
        if last and not last[2] and height < last[1] + self.p.pause_max:
            raise RuleViolation("re-pause cooldown: needs a ratifying vote")
        end = height + duration
        self.tr.paused_until[project] = end
        self.history.setdefault(project, []).append((height, end, False))
        self.reg._log(height, Actor.agent(agent), "PAUSE", project, reason)
        return end

    def ratify(self, actor: Actor, project: str, height: int, extend_to: int) -> None:
        """A passed vote extends a live pause to `extend_to` (e.g. through a corrective vote)."""
        last = self._last(project)
        if not last or height >= last[1]:
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
