"""Assignment 7, Part C, task 7: where each failed run first went wrong (slide 29).

    python -m eval.failures            # the table, and eval/golden/v1/failures.md
    python -m eval.failures --grid     # just the two grids

For every run of either arm whose grounded check failed, the **first** wrong step, not
the step where the run finally broke. A run that reads the wrong file and then writes a
comment about it has one fault, at the read; marking the comment would send the fix to
the wrong place.

`last_good` is the name of the call before the first wrong one, or `start` when the
first call was already wrong. `first_wrong` is the name of the first wrong call, or
`stop` when the run ended before a call it needed (section 15.7).

The rules below decide it from the trace and the facts the grounded check reported.
They are rules rather than judgement calls so that the grid can be recomputed, and so
that a reader can disagree with the rule rather than with an opinion.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from harness import ROOT
from harness.tasks import load_tasks
from harness.trace import read_trace

from eval.grounded import check_run
from eval.metrics import WRITES, canonical

RESULTS = ROOT / "results"
REVIEW = ROOT / "eval" / "golden" / "v1" / "failures.md"
START, STOP = "start", "stop"

# The tool that writes each thing a task's expect names, by RepoMind's registry names.
NEEDED = {"comment": "issues_comment", "labels": "issues_label", "pull_request": "pulls_open"}


def _calls(trace: list[dict]) -> list[dict]:
    return [line for line in trace if line.get("type") == "tool_call"]


def _at(calls: list[dict], i: int) -> tuple[str, str]:
    """The pair (last_good, first_wrong) when call `i` is the first wrong one."""
    return (calls[i - 1]["name"] if i > 0 else START), calls[i]["name"]


def first_wrong(trace: list[dict], task, facts: dict) -> tuple[str, str, str]:
    """(last_good, first_wrong, why) for one failed run, by the rules below, in order."""
    calls = _calls(trace)
    wrong = {name for name, value in facts.items() if value == "wrong"}
    missing = {name for name, value in facts.items() if value == "missing"}
    names = [c["name"] for c in calls]

    # 1. No call at all. Nothing went wrong in the trajectory; the trajectory is absent.
    if not calls:
        return START, STOP, "the run made no tool call at all (slide 28)"

    # 2. A task whose right move was to change nothing, and the run wrote. The first
    #    write is the fault, however sensible the reading before it was.
    if task.decision == "stop":
        for i, call in enumerate(calls):
            if call["name"] in WRITES:
                return (*_at(calls, i), f"the task expects no change, and {call['name']} wrote to the tracker")

    # 3. A call to a tool the task never needed: the run left its route here.
    expected = set(task.reference["tools"])
    for i, call in enumerate(calls):
        if call["name"] not in expected:
            return (*_at(calls, i), f"{call['name']} is not among the tools this task needs")

    # 4. A call identical to an earlier one: the run stopped making progress here.
    seen = set()
    for i, call in enumerate(calls):
        key = (call["name"], canonical(call.get("input")))
        if key in seen:
            return (*_at(calls, i), f"{call['name']} repeats an earlier call with the same arguments")
        seen.add(key)

    # 5. Something the task expects was never written, and the tool that writes it was
    #    never called: the run ended before a call it needed.
    for fact in ("comment", "labels", "pull_request"):
        if fact in missing and NEEDED[fact] not in names:
            return names[-1], STOP, f"the run ended without calling {NEEDED[fact]}, so {fact} is missing"

    # 6. The comment names the wrong file. The fault is the read the run took for its
    #    answer: the last file it opened before writing, not the writing of it.
    if "comment" in wrong or "pull_request" in wrong:
        reads = [i for i, c in enumerate(calls) if c["name"] == "code_read_file"]
        if reads:
            i = reads[-1]
            return (*_at(calls, i), "the run took this read for its answer and stopped looking")
        searches = [i for i, c in enumerate(calls) if c["name"] == "code_search"]
        if searches:
            i = searches[-1]
            return (*_at(calls, i), "the run answered from this search without opening a file")

    # 7. A write landed but left the wrong thing behind.
    for fact in ("labels", "pull_request", "comment"):
        if fact in wrong and NEEDED[fact] in names:
            i = names.index(NEEDED[fact])
            return (*_at(calls, i), f"{NEEDED[fact]} wrote, and left {fact} wrong")

    # 8. A prohibited write: closed, merged, pushed, wrote elsewhere, or leaked a secret.
    for i, call in enumerate(calls):
        if call["name"] in WRITES - {"issues_comment", "issues_label", "pulls_open"}:
            return (*_at(calls, i), f"{call['name']} is a write this task's decision forbids")

    return names[-1], STOP, "the run finished with a fact still missing and no call left to make"


def failures(results: Path = RESULTS, tasks_dir: str = "eval/golden/v1/tasks",
             prefix: str = "") -> list[dict]:
    """One entry per failed run of either arm, in run order (section 15.7).

    `prefix` is "scripted_" to read the free rehearsal's results instead of the real
    ones, so the rules below can be exercised before a token is spent."""
    by_id = {t.id: t for t in load_tasks(tasks_dir)}
    out = []
    for arm in ("A", "B"):
        path = results / f"{prefix}{arm}.jsonl"
        if not path.exists():
            continue
        for line in (json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()):
            if line.get("passed"):
                continue
            task = by_id[line["task"]]
            trace = read_trace(ROOT / "runs" / f"{line['run_id']}.jsonl")
            # The per-fact detail, recomputed from the tracker rather than carried on
            # the results line, which section 15.4 fixes to a present/total count.
            graded = check_run(line["run_id"], task)
            last_good, wrong, why = first_wrong(trace, task, graded["facts"])
            out.append({"run_id": line["run_id"], "arm": arm, "last_good": last_good,
                        "first_wrong": wrong, "_task": line["task"], "_why": why})
    return out


def grid(entries: list[dict]) -> dict:
    """{arm: {last_good: {first_wrong: count}}}, zero cells left out (section 15.7)."""
    out: dict = {}
    for f in entries:
        rows = out.setdefault(f["arm"], {}).setdefault(f["last_good"], {})
        rows[f["first_wrong"]] = rows.get(f["first_wrong"], 0) + 1
    return out


def render(entries: list[dict]) -> str:
    lines = ["# Where each failed run first went wrong",
             "",
             "Produced by `python -m eval.failures`. One row per run of either arm whose grounded",
             "check failed, with the rule that decided it. The grid in `reports/LAB_07.json` is",
             "counted from this same list, so the two cannot disagree.",
             "",
             "| Run | Arm | Task | Last good step | First wrong step | Why |",
             "|---|---|---|---|---|---|"]
    for f in entries:
        lines.append(f"| `{f['run_id']}` | {f['arm']} | {f['_task']} | `{f['last_good']}` | "
                     f"`{f['first_wrong']}` | {f['_why']} |")
    if not entries:
        lines.append("| | | | | | no run of either arm failed its grounded check |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--grid", action="store_true", help="print the two grids and nothing else")
    a = p.parse_args(argv)
    entries = failures()
    if a.grid:
        print(json.dumps(grid(entries), indent=2))
        return 0
    print(render(entries))
    REVIEW.write_text(render(entries), encoding="utf-8")
    print(f"wrote {REVIEW.relative_to(ROOT)}: {len(entries)} failed runs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
