"""Assignment 7, Part A, task 1: the recorded runs, rendered for reading.

    python -m eval.digest > digest.txt         # all 60, one section each
    python -m eval.digest --brief              # the same, one line per call
    python -m eval.digest <run_id>             # one run, in full

This scores nothing and decides nothing. It lays out each recorded run in
fixtures/traces7/ so its first wrong step can be found by reading: the run's way and
issue, every tool call in order with its input and what it returned, the comment it
posted if it posted one, and the end state it left. Slide 27's fixture is left out; it
is not one of the sixty.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from harness import ROOT

TRACES = ROOT / "fixtures" / "traces7"
RESULT_CHARS = 600


def run_ids(root: Path = ROOT) -> list[str]:
    """The sixty recorded runs, by ID, in order."""
    traces = (root / "fixtures" / "traces7").glob("*.jsonl")
    return sorted(p.stem for p in traces if not p.name.startswith("s27"))


def lines_of(run_id: str, root: Path = ROOT) -> list[dict]:
    path = root / "fixtures" / "traces7" / f"{run_id}.jsonl"
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def end_state_of(run_id: str, root: Path = ROOT) -> dict:
    path = root / "fixtures" / "traces7" / f"{run_id}.state.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _clip(text: str, limit: int = RESULT_CHARS) -> str:
    text = str(text or "").replace("\n", "\n      ")
    return text if len(text) <= limit else text[:limit] + f" ... [{len(text):,} chars]"


def render(run_id: str, root: Path = ROOT) -> str:
    lines = lines_of(run_id, root)
    start = lines[0] if lines else {}
    out = [f"{'=' * 100}",
           f"{run_id}   way={start.get('way')}   issue={start.get('issue')}   model={start.get('model')}"]

    calls = [x for x in lines if x.get("type") == "tool_call"]
    out.append(f"-- {len(calls)} tool calls --")
    for i, c in enumerate(calls, 1):
        flag = "  ERROR" if c.get("is_error") else ""
        out.append(f"  {i:>2}. {c.get('name')}({json.dumps(c.get('input'), ensure_ascii=False)}){flag}")
        out.append(f"      -> {_clip(c.get('result') or c.get('result_excerpt'))}")

    ends = [x for x in lines if x.get("type") == "end"]
    if ends:
        out.append(f"-- ended: {', '.join(str(e.get('terminal_reason')) for e in ends)}"
                   f" ({'; '.join(str(e.get('detail') or '') for e in ends)}) --")

    state = (end_state_of(run_id, root).get("state") or {})
    out.append("-- end state --")
    for issue, s in state.items():
        out.append(f"  issue {issue}: labels={s.get('labels')} prs={len(s.get('prs') or [])} "
                   f"closed={s.get('closed')} merges={s.get('merges')} "
                   f"pushes={len(s.get('pushes') or [])} elsewhere={s.get('elsewhere')}")
        for body in s.get("comments") or []:
            out.append(f"  comment: {_clip(body, 900)}")
        for pr in s.get("prs") or []:
            out.append(f"  pr: {pr.get('title')} | {_clip(pr.get('body'), 300)}")
    return "\n".join(out)


_KEY_ARGS = ("issue", "path", "query", "branch", "title", "label", "pull_request")
_COUNT = re.compile(r'"count":\s*(\d+)')


def _short_input(call: dict) -> str:
    """A call's arguments, shortened to the ones that say what it asked for."""
    got = call.get("input") or {}
    parts = [f"{k}={got[k]!r}" for k in _KEY_ARGS if got.get(k) not in (None, "")]
    return ", ".join(parts) or json.dumps(got, ensure_ascii=False)[:80]


def _outcome(call: dict) -> str:
    """What the call returned, in a few words: a search's hit count, a write's effect."""
    result = str(call.get("result") or call.get("result_excerpt") or "")
    if call.get("is_error"):
        return f"ERROR {result[:120]}"
    hits = _COUNT.search(result)
    if hits:
        return f"{hits.group(1)} hits"
    return f"{len(result):,} chars"


def brief(run_id: str, root: Path = ROOT) -> str:
    lines = lines_of(run_id, root)
    start = lines[0] if lines else {}
    calls = [x for x in lines if x.get("type") == "tool_call"]
    ends = [str(x.get("terminal_reason")) for x in lines if x.get("type") == "end"]
    out = [f"--- {run_id}  way={start.get('way')}  issue={start.get('issue')}  "
           f"calls={len(calls)}  ended={','.join(ends) or 'none'}"]
    for i, c in enumerate(calls, 1):
        out.append(f"   {i:>2}. {c.get('name'):<16} {_short_input(c):<70.70} -> {_outcome(c)}")

    state = (end_state_of(run_id, root).get("state") or {})
    for issue, s in state.items():
        comments = s.get("comments") or []
        head = " | ".join(x.strip() for x in (comments[0].splitlines()[:2] if comments else [])) or "no comment"
        out.append(f"   STATE {issue}: {head}")
        out.append(f"   STATE {issue}: labels={s.get('labels')} prs={len(s.get('prs') or [])} "
                   f"comments={len(comments)} closed={s.get('closed')} merges={s.get('merges')} "
                   f"pushes={[p.get('branch') for p in s.get('pushes') or []]} elsewhere={s.get('elsewhere')}")
        for pr in s.get("prs") or []:
            out.append(f"   STATE {issue}: pr {str(pr.get('title'))[:90]}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    short = "--brief" in argv
    wanted = [a for a in argv if not a.startswith("-")] or run_ids()
    for run_id in wanted:
        print(brief(run_id) if short else render(run_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
