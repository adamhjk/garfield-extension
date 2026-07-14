from __future__ import annotations

from garfield_bench.models import Case

from .base import CoordinatorAdapter


class GarfieldAdapter(CoordinatorAdapter):
    treatment = "garfield"

    def prompts(self, case: Case, work_item: str) -> list[str]:
        common = f"""{case.prompt}

Before any other action, read `.agents/skills/garfield/SKILL.md` completely and
follow it as the explicitly requested `garfield` skill. You have authority to
edit the working copy and must use the skill's review/fix/validation
coordination. The benchmark work item is `{work_item}`. Hidden tests are outside
this workspace; do not search for them.
"""
        if not case.forced_restart:
            return [common + "\nContinue until Garfield reaches its normal terminal handoff."]
        first = common + """

Forced-restart protocol: perform scope, review, and the first material fix.
After that fix is applied and focused validation has run, stop before the next
review cycle and end with `<garfield-bench-restart/>`. This protocol overrides
the normal instruction to continue looping in this first session only.
"""
        second = f"""{case.prompt}

This is a fresh coordinator replacing a terminated one for benchmark work item
`{work_item}`. Before any other action, read
`.agents/skills/garfield/SKILL.md` completely and follow it as the explicitly
requested `garfield` skill. Reconstruct intent and current diff only from the
working copy and prompt, then continue the review/fix/validate loop to its
normal terminal handoff. Do not search for hidden tests.
"""
        return [first, second]
