"""Assignment 7, Part D: the judge, its rates and its correction (checks/FORMATS.md,
section 15.10).

    python -m eval.judge test 1        # run 1 on the test set: eval/judge/verdicts/test_1.jsonl
    python -m eval.judge versions      # the test items' list and long versions: versions.jsonl
    python -m eval.judge recorded      # the agent way's recorded comments: recorded.jsonl

Your judge reads one output, its issue and what RepoMind's tools returned, and
answers with slide 36's fixed reply: JSON with a one-line "reasoning", then an
"answer", "Pass" or "Fail". Every call goes through a metered judge session, so its
tokens and cost are recorded and priced, and count against lab_token_ceiling:

    from harness.meter import judge_session
    with judge_session("test-1") as session:
        response = session.client.create(system=prompt, messages=[{"role": "user", "content": text}])
        session.trace.model_call(0, response, purpose="judge")

Write session.id on every verdict line. To test the plumbing for nothing, pass
backend="harness.scripted:PassEverything", a judge that passes everything: a coin.

The checker calls `correct`, `rates` and `bootstrap` on cases of its own, and
`correct` on a coin, so keep their names, arguments and returns.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
from pathlib import Path

import yaml

from harness import ROOT
from harness.meter import judge_session
from harness.trace import read_trace

OUTPUTS = ROOT / "fixtures" / "judge" / "outputs"
VERDICTS = ROOT / "eval" / "judge" / "verdicts"
PROMPT = ROOT / "prompts" / "judge.md"
SPLIT = ROOT / "eval" / "labels" / "split.yaml"
TRACES = ROOT / "fixtures" / "traces7"
COMMENT_WRITES = frozenset({"post_comment", "issues_comment"})

# A judge whose two rates sum to this close to 1 is no better than a coin (slide 44).
COIN_BAND = 0.1
# How many resamples the bootstrap draws, and why each dropped draw was dropped.
RESAMPLES = 2000
last_bootstrap_drops: dict[str, int] = {}


class CoinJudge(ValueError):
    """TPR + TNR is within 0.1 of 1: the judge is no better than a coin. Fix it, do not
    correct it (slide 44)."""


def correct(p: float, tpr: float, tnr: float) -> float:
    """The share you would pass, labelling by hand, from the judge's pass rate p on
    outputs nobody labelled: (p + TNR - 1) / (TPR + TNR - 1) (slide 44), clipped to
    0 to 1. Raises CoinJudge when TPR + TNR is within 0.1 of 1.

    The clip is not cosmetic. A share cannot leave 0 to 1, but the formula can, when p
    is higher or lower than the test set's rates allow; a corrected rate sitting exactly
    at 1 or 0 is the formula saying so, and the bootstrap interval carries the rest.
    """
    if abs(tpr + tnr - 1) <= COIN_BAND:
        raise CoinJudge(f"TPR {tpr:.3f} + TNR {tnr:.3f} = {tpr + tnr:.3f}, within {COIN_BAND} of 1: "
                        "this judge is no better than a coin, so its rate cannot be corrected")
    return min(1.0, max(0.0, (p + tnr - 1) / (tpr + tnr - 1)))


def rates(verdicts: dict[str, str], labels: dict[str, str]) -> tuple[float, float]:
    """(TPR, TNR) of the judge's verdicts against your labels, each "pass" or "fail",
    on the items both cover (slide 43): TPR is the share of the labelled passes the
    judge passed, TNR the share of the labelled fails it failed."""
    passes = [i for i in labels if labels[i] == "pass" and i in verdicts]
    fails = [i for i in labels if labels[i] == "fail" and i in verdicts]
    return (sum(verdicts[i] == "pass" for i in passes) / len(passes) if passes else 0.0,
            sum(verdicts[i] == "fail" for i in fails) / len(fails) if fails else 0.0)


def bootstrap(verdicts: dict[str, str], labels: dict[str, str], p: float,
              resamples: int = RESAMPLES, seed: int = 0) -> tuple[float, float]:
    """The middle 95% of the corrected rate over resamples of the test items, drawn
    with replacement, as many as there are, each time recomputing TPR and TNR
    (slide 44). A resample on which the judge is a coin is left out.

    Two kinds of draw are dropped rather than scored: one holding no passes or no
    fails, where TPR or TNR is undefined, and one on which the judge comes out a coin,
    where the correction is undefined too. Dropping them narrows the interval, so the
    count of each is left in `last_bootstrap_drops` and reported beside the interval.
    """
    items = [i for i in labels if i in verdicts]
    rng = random.Random(seed)
    got: list[float] = []
    dropped = {"one_sided": 0, "coin": 0}
    for _ in range(resamples):
        draw = [rng.choice(items) for _ in items]
        n_pass = sum(labels[i] == "pass" for i in draw)
        n_fail = len(draw) - n_pass
        if not n_pass or not n_fail:
            dropped["one_sided"] += 1
            continue
        tpr = sum(labels[i] == "pass" and verdicts[i] == "pass" for i in draw) / n_pass
        tnr = sum(labels[i] == "fail" and verdicts[i] == "fail" for i in draw) / n_fail
        if abs(tpr + tnr - 1) <= COIN_BAND:
            dropped["coin"] += 1
            continue
        got.append(min(1.0, max(0.0, (p + tnr - 1) / (tpr + tnr - 1))))
    got.sort()
    last_bootstrap_drops.clear()
    last_bootstrap_drops.update(dropped, kept=len(got), resamples=resamples)
    if not got:
        return None, None
    return got[int(0.025 * (len(got) - 1))], got[int(0.975 * (len(got) - 1))]


def load_outputs(root: Path = ROOT) -> dict[str, dict]:
    """The 60 outputs to label, by ID (section 15.9)."""
    return {p.stem: json.loads(p.read_text(encoding="utf-8"))
            for p in sorted((root / "fixtures" / "judge" / "outputs").glob("*.json"))}


# -- asking the judge ----------------------------------------------------------------

def question(issue: dict, evidence: list[dict], comment: str) -> str:
    """One output as the judge sees it: the issue, every tool result, then the comment."""
    parts = [f"## THE ISSUE (#{issue.get('number')})", f"{issue.get('title')}", "",
             str(issue.get("body") or "").strip(), "",
             f"## WHAT REPOMIND'S TOOLS RETURNED ({len(evidence)} calls, in order)", ""]
    for i, call in enumerate(evidence, 1):
        parts += [f"### [{i}] {call['tool']}  input: {json.dumps(call['input'], ensure_ascii=False)}",
                  str(call["result"]).strip(), ""]
    parts += ["## THE COMMENT TO JUDGE", str(comment).strip()]
    return "\n".join(parts)


def parse_reply(text: str) -> dict | None:
    """The judge's fixed reply, recovered from whatever wrapped it.

    The model will sometimes put the object in a fence or add a sentence around it, so
    the first `{` through the last `}` is taken and parsed. None when no object can be
    recovered, which the caller turns into one retry.
    """
    if not text:
        return None
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        got = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    answer = str(got.get("answer", "")).strip().lower()
    if answer not in ("pass", "fail"):
        return None
    return {"answer": answer, "reasoning": str(got.get("reasoning", "")).strip()[:400]}


def ask(session, prompt: str, text: str) -> dict:
    """One verdict. One retry when the reply cannot be parsed, then a recorded failure
    rather than an abandoned sweep of twenty-five."""
    for attempt in (1, 2):
        response = session.client.create(system=prompt, messages=[{"role": "user", "content": text}])
        session.trace.model_call(attempt - 1, response, purpose="judge")
        got = parse_reply(response.text)
        if got is not None:
            return got
    return {"answer": "fail", "reasoning": f"[unparsed reply] {str(response.text)[:200]}"}


def served_model(session) -> str:
    """The dated snapshot the API actually served, from the session's model_call lines.

    settings.yaml names an alias (`gpt-4o-mini`), and meter.py puts that alias on the
    run_start line, but a judge is its model *at a pinned version* (slide 41). The
    model_call lines carry what the API returned, which is the dated snapshot.
    """
    path = ROOT / "runs" / "judge" / f"{session.id}.jsonl"
    if not path.exists():
        return session.model
    served = [line.get("model") for line in read_trace(path) if line.get("type") == "model_call"]
    return served[-1] if served and served[-1] else session.model


def write_verdicts(name: str, rows: list[dict]) -> Path:
    VERDICTS.mkdir(parents=True, exist_ok=True)
    path = VERDICTS / f"{name}.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def test_ids() -> list[str]:
    return list(yaml.safe_load(SPLIT.read_text(encoding="utf-8"))["test"])


def recorded_with_comment() -> list[tuple[str, str]]:
    """(run_id, the body of its last comment) for every recorded run of the agent way
    that posted one. The other ways' comments cite nothing and would pass whatever the
    judge is worth."""
    out = []
    for path in sorted(TRACES.glob("*.jsonl")):
        if path.name.startswith("s27"):
            continue
        lines = read_trace(path)
        if not lines or lines[0].get("way") != "agent":
            continue
        comments = [x for x in lines if x.get("type") == "tool_call"
                    and x.get("name") in COMMENT_WRITES and not x.get("is_error")]
        if comments:
            out.append((lines[0].get("run_id") or path.stem,
                        str((comments[-1].get("input") or {}).get("body") or "")))
    return out


def recorded_evidence(run_id: str) -> tuple[dict, list[dict]]:
    """A recorded run's issue and the calls it made before its comment, in the shape
    `question` wants, so a recorded comment is judged exactly as a fixture output is."""
    lines = read_trace(TRACES / f"{run_id}.jsonl")
    calls = [x for x in lines if x.get("type") == "tool_call"]
    before, issue_text = [], ""
    for call in calls:
        if call.get("name") in COMMENT_WRITES:
            break
        before.append({"tool": call.get("name"), "input": call.get("input") or {},
                       "result": call.get("result") or call.get("result_excerpt") or ""})
        if call.get("name") == "issues_read" and not issue_text:
            issue_text = str(call.get("result") or "")
    number = lines[0].get("issue")
    title = issue_text.splitlines()[0] if issue_text else f"issue-{number}"
    return {"number": number, "title": title, "body": issue_text}, before


def run_set(name: str, backend: str | None, items: list[tuple[str, str, dict, list[dict], dict]]) -> None:
    """Judge a list of (id, comment, issue, evidence, extra) in one metered session."""
    prompt = PROMPT.read_text(encoding="utf-8")
    rows = []
    with judge_session(name, backend=backend) as session:
        for item_id, comment, issue, evidence, extra in items:
            got = ask(session, prompt, question(issue, evidence, comment))
            rows.append({"id": item_id, **got, "session": session.id, "model": "", **extra})
            print(f"  {item_id}: {got['answer']}")
        model = served_model(session)
    for row in rows:
        row["model"] = model
    path = write_verdicts(name.replace("-", "_"), rows)
    print(f"wrote {path.relative_to(ROOT)}: {len(rows)} verdicts on {model}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("what", choices=["test", "versions", "recorded"])
    p.add_argument("run", nargs="?", type=int, choices=[1, 2, 3], help="which of the three test runs")
    p.add_argument("--backend", help="harness.scripted:PassEverything to test the plumbing for free")
    a = p.parse_args(argv)
    outputs = load_outputs()

    if a.what == "test":
        if a.run is None:
            raise SystemExit("python -m eval.judge test <1|2|3>")
        items = [(i, outputs[i]["comment"], outputs[i]["issue"], outputs[i]["evidence"], {})
                 for i in test_ids()]
        run_set(f"test-{a.run}", a.backend, items)
    elif a.what == "versions":
        items = [(i, outputs[i]["versions"][v], outputs[i]["issue"], outputs[i]["evidence"], {"version": v})
                 for i in test_ids() for v in ("list", "long")]
        run_set("versions", a.backend, items)
    else:
        items = []
        for run_id, comment in recorded_with_comment():
            issue, evidence = recorded_evidence(run_id)
            items.append((run_id, comment, issue, evidence, {}))
        run_set("recorded", a.backend, items)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
