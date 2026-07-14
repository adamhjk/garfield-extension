from __future__ import annotations

from garfield_bench.models import Case

from .base import CoordinatorAdapter


class SwampGarfieldAdapter(CoordinatorAdapter):
    treatment = "swamp-garfield"

    def prompts(self, case: Case, work_item: str) -> list[str]:
        common = f"""{case.prompt}

Before any other action, read `.agents/skills/swamp-garfield/SKILL.md`
completely and follow it as the explicitly requested `swamp-garfield` skill;
do not substitute the generic `swamp` skill. Drive the configured model named
`swamp-garfield` for stable work-item reference `{work_item}`. The
`SWAMP_REPO_DIR` environment variable points at this run's isolated control
repository. Select the existing `validate-slice` workflow and only applicable
Ledgerlite repository skills. Hidden tests are outside this workspace; do not
search for them.
"""
        if not case.forced_restart:
            return [common + "\nContinue until the factory reaches a terminal state."]
        first = common + """

Forced-restart protocol: drive through the first material fixing stage. Once
the fix result is persisted and the factory has advanced back to `scope`, stop
and end with `<garfield-bench-restart/>`. Do not continue the next scope cycle
in this first session.
"""
        second = f"""{case.prompt}

This is a fresh coordinator replacing a terminated one. Before any other
action, read `.agents/skills/swamp-garfield/SKILL.md` completely and follow it
as the explicitly requested `swamp-garfield` skill; do not substitute the
generic `swamp` skill. Resume existing work item `{work_item}` strictly from
the factory's compact `status`; never call `start` for the existing run.
Continue to the terminal state using `validate-slice`. Hidden tests are outside
this workspace.
"""
        return [first, second]
