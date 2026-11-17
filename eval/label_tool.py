"""Assignment 7, Part D, task 2: label the sixty outputs by hand.

    python -m eval.label_tool              # start, or carry on where you stopped
    python -m eval.label_tool --review j07 # look at one output again
    python -m eval.label_tool --status     # how many are done

It shows one output at a time: the issue, every tool call the run made before its
comment with what each returned, and then the comment. You answer `pass` or `fail` and
give a one-line reason, and the row is appended to eval/labels/labels.csv at once, so an
interrupted session loses nothing.

No model is involved and nothing is suggested, ranked or pre-filled. These labels are
what the judge is measured against, so a suggested label would be measuring the
suggestion. Type `?` to reread the criterion, `s` to skip an output for now, and `q` to
stop.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from harness import ROOT

OUTPUTS = ROOT / "fixtures" / "judge" / "outputs"
LABELS = ROOT / "eval" / "labels" / "labels.csv"
CRITERION = ROOT / "eval" / "judge" / "criterion.md"
RULE = "=" * 100


def load_outputs() -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(OUTPUTS.glob("*.json"))}


def read_labels() -> dict[str, dict]:
    if not LABELS.exists():
        return {}
    with LABELS.open(newline="", encoding="utf-8") as fh:
        return {row["id"]: row for row in csv.DictReader(fh) if row.get("id")}


def append(row_id: str, label: str, reason: str) -> None:
    LABELS.parent.mkdir(parents=True, exist_ok=True)
    new = not LABELS.exists()
    with LABELS.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if new:
            writer.writerow(["id", "label", "reason"])
        writer.writerow([row_id, label, reason])
        fh.flush()


def show(out: dict) -> None:
    """One output, laid out for reading: the issue, the evidence, then the comment.

    Which system wrote the comment is deliberately not shown. It stays in the corpus,
    where make_split.py needs it to balance the three sets, but on screen it could only
    sway a verdict the criterion answers the same way for either system.
    """
    issue = out["issue"]
    print(f"\n{RULE}\n{out['id']}\n{RULE}")
    print(f"\nISSUE #{issue['number']}: {issue['title']}\n")
    print(issue["body"].rstrip())
    print(f"\n{'-' * 100}\nEVIDENCE: {len(out['evidence'])} calls, in order, with what each returned\n")
    for i, call in enumerate(out["evidence"], 1):
        print(f"[{i}] {call['tool']}({json.dumps(call['input'], ensure_ascii=False)})")
        for line in str(call["result"]).splitlines():
            print(f"      {line}")
        print()
    print(f"{'-' * 100}\nTHE COMMENT\n")
    print(out["comment"].rstrip())
    print(f"\n{RULE}")


def ask(row_id: str) -> tuple[str, str] | None:
    """One answer: pass or fail, then a reason. None to skip, SystemExit to stop."""
    while True:
        answer = input(f"{row_id}  pass / fail  (? criterion, s skip, q quit) > ").strip().lower()
        if answer in ("q", "quit"):
            raise SystemExit("stopped; everything answered so far is saved")
        if answer in ("s", "skip"):
            return None
        if answer == "?":
            print("\n" + CRITERION.read_text(encoding="utf-8") + "\n")
            continue
        if answer in ("pass", "fail", "p", "f"):
            label = "pass" if answer.startswith("p") else "fail"
            reason = ""
            while not reason:
                reason = input("  reason, one line, how you know > ").strip()
            return label, reason
        print("  answer pass or fail.")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--review", metavar="ID", help="show one output again, without labelling it")
    p.add_argument("--status", action="store_true", help="how many of the sixty are labelled")
    a = p.parse_args(argv)

    outputs, done = load_outputs(), read_labels()
    if a.review:
        show(outputs[a.review])
        if a.review in done:
            print(f"labelled {done[a.review]['label']}: {done[a.review]['reason']}")
        return 0
    if a.status:
        left = [i for i in outputs if i not in done]
        print(f"{len(done)} of {len(outputs)} labelled; {len(left)} left"
              + (f": {', '.join(left[:12])}" if left else ""))
        return 0

    todo = [i for i in outputs if i not in done]
    if not todo:
        print(f"all {len(outputs)} outputs are labelled in {LABELS.relative_to(ROOT)}")
        return 0
    print(f"{len(done)} labelled, {len(todo)} to go. The criterion is {CRITERION.relative_to(ROOT)}.")

    for row_id in todo:
        show(outputs[row_id])
        answer = ask(row_id)
        if answer is None:
            continue
        append(row_id, *answer)
        print(f"  saved {answer[0]}")
    print(f"\n{len(read_labels())} of {len(outputs)} labelled.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyboardInterrupt, EOFError):
        sys.exit("\nstopped; everything answered so far is saved")
