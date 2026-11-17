"""Assignment 7, Part B, task 1: one line per run, in results/<arm>.jsonl
(checks/FORMATS.md, section 15.4).

    python -m eval.results_07 --arm A --way planned --claim plan
    python -m eval.results_07 --arm B --way planned --switch TOOL_EXAMPLES=off --claim examples

Reads the arm's finished runs on your subset's golden tasks in runs/, checks each with your
grounded check, computes Part C's measure and the five metrics, and writes one line
per run. The helpers below find the runs and read them; the rest is yours.

A line (section 15.4):

    {"arm": "A", "way": "planned", "switches": {...}, "run_id": "...", "task": "g07",
     "stratum": "routine", "sweep": 1, "passed": true, "facts": {"present": 6, "total": 6},
     "measure": 0, "tokens": 31234, "cost_usd": 0.0412, "wall_clock_s": 18.2,
     "metrics": {"step_count": 2, "precision": 1.0, "recall": 1.0, "repeats": 0,
                 "orphans": 1, "no_tools": false, "cost_usd": 0.0412, "latency_s": 18.2}}

Part C's measure, per run, by claim (section 15.4): tokens, the run_end line's
totals.total_tokens; plan, the run's repeats; examples, its wasted calls: the lines of
its call record (runs/<run_id>.calls.jsonl) whose outcome is "rejected", "error" or
"protocol", plus the search calls whose result has "count": 0; checkpoint, its duplicate
writes: the comments beyond one, plus the open pull requests beyond one, on its issue
in its end state; split, 100 when the run passed and 0 when it did not.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from harness import LAB, ROOT
from harness import switches as switch_board
from harness.formats import UNFINISHED
from harness.tasks import load_tasks, read_subset
from harness.trace import read_trace

# A call the registry's boundary refused, one that failed in the tool, and one that named
# no tool: the three outcomes that waste a call (section 15.4).
WASTED_OUTCOMES = ("rejected", "error", "protocol")
SEARCH_EMPTY = re.compile(r'"count":\s*0\b')


def finished_runs(way: str, switches: dict | None = None, root: Path = ROOT,
                  scripted: bool = False) -> list[list[dict]]:
    """Every finished Assignment 7 run of `way` with these switches (unset ones at their
    defaults), on a real model, as its trace's lines: one list per run. A run is finished
    when its last line is run_end and it did not end quota or rate_limited. With
    scripted=True, the runs on a scripted model instead, to test your code for free."""
    want = {**switch_board.DEFAULTS, **(switches or {})}
    out = []
    for path in sorted((root / "runs").glob("*.jsonl")):
        if path.name.startswith("_") or path.name.count(".") > 1:
            continue
        lines = read_trace(path)
        start = lines[0] if lines else {}
        if start.get("type") != "run_start" or start.get("lab") != LAB or start.get("way") != way:
            continue
        if {**switch_board.DEFAULTS, **(start.get("switches") or {})} != want:
            continue
        free = str(start.get("backend", "")).startswith("harness.scripted:") or start.get("backend") == "never-stops"
        if free != scripted:
            continue
        ends = [r.get("terminal_reason") for r in lines if r.get("type") == "end"]
        if lines[-1].get("type") != "run_end" or set(ends) & set(UNFINISHED):
            continue
        out.append(lines)
    return out


def call_record(run_id: str, root: Path = ROOT) -> list[dict]:
    """A run's call record, runs/<run_id>.calls.jsonl, one dict per line."""
    path = root / "runs" / f"{run_id}.calls.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def wasted(run_id: str, root: Path = ROOT) -> int:
    """The claim's measure for `examples`: the calls the registry's boundary refused,
    that failed in the tool, or that named no tool, and the searches that found
    nothing (section 15.4)."""
    out = 0
    for line in call_record(run_id, root):
        if line.get("outcome") in WASTED_OUTCOMES:
            out += 1
        elif line.get("role") == "search" and SEARCH_EMPTY.search(str(line.get("result") or "")):
            out += 1
    return out


def duplicate_writes(state: dict, issue: int) -> int:
    """The claim's measure for `checkpoint`: the comments beyond one, plus the open pull
    requests beyond one, on the task's issue."""
    where = state.get(issue) or state.get(str(issue)) or {}
    return max(0, len(where.get("comments") or []) - 1) + max(0, len(where.get("prs") or []) - 1)


def measure_of(claim: str, trace: list[dict], task, graded: dict, counted: dict, state: dict):
    """Part C's measure for one run, by claim (section 15.4)."""
    end = [line for line in trace if line.get("type") == "run_end"][-1]
    run_id = trace[0].get("run_id")
    if claim == "tokens":
        return int((end.get("totals") or {}).get("total_tokens") or 0)
    if claim == "plan":
        return counted["repeats"]
    if claim == "examples":
        return wasted(run_id)
    if claim == "checkpoint":
        return duplicate_writes(state, task.issues[0])
    return 100 if graded["passed"] else 0


def result_line(arm: str, way: str, trace: list[dict], task, claim: str) -> dict:
    """One run as a line of results/<arm>.jsonl (section 15.4)."""
    from harness.tasks import end_state
    from harness.tracker import Tracker

    from eval.grounded import check
    from eval.metrics import metrics

    start, run_id = trace[0], trace[0].get("run_id")
    end = [line for line in trace if line.get("type") == "run_end"][-1]
    totals = end.get("totals") or {}

    state = end_state(Tracker(flaky=False, readback_fail=False), run_id, task)
    graded = check(task, state)
    counted = metrics(trace, task)

    return {"arm": arm, "way": way, "switches": {**switch_board.DEFAULTS, **(start.get("switches") or {})},
            "run_id": run_id, "task": task.id, "stratum": task.stratum, "sweep": start.get("sweep"),
            "passed": bool(graded["passed"]),
            "facts": {"present": sum(v == "present" for v in graded["facts"].values()),
                      "total": len(graded["facts"])},
            "measure": measure_of(claim, trace, task, graded, counted, state),
            "tokens": int(totals.get("total_tokens") or 0),
            "cost_usd": float(totals.get("cost_usd") or 0.0),
            "wall_clock_s": float(end.get("elapsed_s") or 0.0),
            "metrics": counted}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--arm", required=True, choices=["A", "B"])
    p.add_argument("--way", required=True)
    p.add_argument("--switch", action="append", default=[], metavar="NAME=VALUE")
    p.add_argument("--claim", required=True, choices=["tokens", "plan", "examples", "checkpoint", "split"])
    p.add_argument("--tasks", default="eval/golden/v1/tasks")
    p.add_argument("--subset", default="eval/subsets/claim.txt", help="only these task IDs (Part C)")
    p.add_argument("--scripted", action="store_true",
                   help="the runs on a scripted model, to test this script for free: writes "
                        "results/scripted_<arm>.jsonl, which the checker never reads")
    a = p.parse_args(argv)
    switches = {}
    for pair in a.switch:
        name, _, value = pair.partition("=")
        switches[name.strip().lower()] = value.strip().lower()

    tasks = {t.id: t for t in load_tasks(a.tasks)}
    wanted = set(read_subset(a.subset)) if a.subset else set(tasks)

    out = ROOT / "results" / f"{'scripted_' if a.scripted else ''}{a.arm}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines, skipped = [], 0
    for trace in finished_runs(a.way, switches, scripted=a.scripted):
        start = trace[0]
        task = tasks.get(start.get("task"))
        if task is None or task.id not in wanted:
            skipped += 1
            continue
        lines.append(result_line(a.arm, a.way, trace, task, a.claim))
    lines.sort(key=lambda r: (r["sweep"] or 0, r["task"]))
    out.write_text("".join(json.dumps(r) + "\n" for r in lines), encoding="utf-8")
    print(f"{out.relative_to(ROOT)}: {len(lines)} runs"
          + (f", {skipped} outside the subset left out" if skipped else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
