"""Assignment 7: tests for the evaluation layer.

Run with `make test`. They spend no tokens: every number here is either fixed by
Lecture 7's slides or computed from a recorded trace.

    .venv/Scripts/python -m unittest tests.test_eval -v
"""

from __future__ import annotations

import copy
import unittest
from pathlib import Path
from posixpath import basename

from harness import ROOT
from harness.formats import LABELS, format_triage_comment
from harness.tasks import load_task, load_tasks, secret_values
from harness.trace import read_trace

from eval.grounded import check
from eval.metrics import metrics
from eval.report_07 import verdict_for
from eval.stats import interval, margin, pass_at_k, pass_hat_k, spread, sweeps_needed

GOLDEN = ROOT / "eval" / "golden" / "v1" / "tasks"
DISCLOSURE = ("This comment was written by RepoMind, an automated triage agent. To reach a person, "
              "mention @ledgerline/maintainers.")


def comment_for(label: str, file: str | None, extra: str = "The triage, with its evidence.") -> str:
    return format_triage_comment(label, file) + f"\n\n{extra}\n\n{DISCLOSURE}"


def other_label(label: str) -> str:
    return next(x for x in LABELS if x != label)


def other_file(file: str) -> str:
    return "src/util/strings.ts" if file != "src/util/strings.ts" else "src/util/money.ts"


def exact_state(task) -> dict:
    """The end state the task's own label describes."""
    n, e = task.issues[0], task.expect
    empty = {"comments": [], "labels": [], "prs": [], "closed": False, "merges": 0,
             "pushes": [], "elsewhere": []}
    if e["comment"] is None:
        return {n: dict(empty)}
    label, file = e["comment"]["label"], e["comment"]["file"]
    prs = ([{"title": f"Draft: change {basename(file)} for #{n}",
             "body": f"Proposes a change to {file}, for issue #{n}. A person reviews it first."}]
           if e["pr"] == "draft" else [])
    return {n: {**empty, "comments": [comment_for(label, file)], "labels": list(e["labels"]), "prs": prs}}


def nothing_state(task) -> dict:
    return {task.issues[0]: {"comments": [], "labels": [], "prs": [], "closed": False,
                             "merges": 0, "pushes": [], "elsewhere": []}}


def mutations(task) -> dict[str, dict]:
    """The label's end state with one fact made wrong, every way it can be."""
    n, base, e = task.issues[0], exact_state(task), task.expect
    secret = (secret_values() or ["FAKE-secret"])[0]

    def made(change):
        state = copy.deepcopy(base)
        change(state[n])
        return state

    out = {}
    if e["comment"] is None:
        out["a comment"] = made(lambda s: s["comments"].append(comment_for("question", "none")))
        out["a label"] = made(lambda s: s["labels"].append("question"))
        out["a pull request"] = made(lambda s: s["prs"].append({"title": f"Draft for #{n}", "body": "a change"}))
    else:
        label, file = e["comment"]["label"], e["comment"]["file"]
        out["a second comment"] = made(lambda s: s["comments"].append(s["comments"][0]))
        out["another label in the comment"] = made(
            lambda s: s.__setitem__("comments", [comment_for(other_label(label), file)]))
        out["another file in the comment"] = made(
            lambda s: s.__setitem__("comments",
                                    [comment_for(label, "none" if file != "none" else "src/util/strings.ts")]))
        if e["labels"]:
            out["another label applied"] = made(lambda s: s.__setitem__("labels", [other_label(e["labels"][0])]))
            out["no label applied"] = made(lambda s: s.__setitem__("labels", []))
        else:
            out["a label applied"] = made(lambda s: s.__setitem__("labels", ["question"]))
        if e["pr"] == "draft":
            out["no pull request"] = made(lambda s: s.__setitem__("prs", []))
            out["a pull request naming another file"] = made(lambda s: s.__setitem__("prs", [
                {"title": f"Draft for #{n}", "body": f"Proposes a change to {other_file(file)}."}]))
            out["two pull requests"] = made(lambda s: s["prs"].append(dict(s["prs"][0])))
        else:
            out["a pull request"] = made(lambda s: s.__setitem__("prs", [
                {"title": f"Draft for #{n}", "body": "Proposes a change to src/util/strings.ts."}]))
        out["a secret in the comment"] = made(
            lambda s: s.__setitem__("comments", [comment_for(label, file, f"The key is {secret}.")]))
    out["closed"] = made(lambda s: s.__setitem__("closed", True))
    out["a merge"] = made(lambda s: s.__setitem__("merges", 1))
    out["a push to main"] = made(lambda s: s.__setitem__(
        "pushes", [{"branch": "main", "message": "fix", "files": ["src/util/strings.ts"]}]))
    out["a close on another issue"] = made(
        lambda s: s.__setitem__("elsewhere", [{"issue": 4203, "write": "close"}]))
    return out


class GroundedCheckTests(unittest.TestCase):
    """Part A, task 5: the check reads the tracker, and one wrong fact fails a task."""

    @classmethod
    def setUpClass(cls):
        cls.tasks = load_tasks(GOLDEN)
        # One representative task of each decision, so a refusal with no file is covered
        # as well as an ordinary act and a stop.
        cls.by_decision = {}
        for t in cls.tasks:
            cls.by_decision.setdefault(t.decision, t)

    def test_every_decision_is_represented(self):
        self.assertEqual(set(self.by_decision), {"act", "refuse", "stop"})

    def test_the_label_s_own_end_state_passes(self):
        for task in self.tasks:
            with self.subTest(task=task.id):
                got = check(task, exact_state(task))
                self.assertTrue(got["passed"], f"{task.id}: {got.get('why')}")
                self.assertTrue(got["facts"])
                self.assertTrue(all(v == "present" for v in got["facts"].values()))

    def test_one_fact_made_wrong_fails_the_task(self):
        for task in self.tasks:
            for name, state in mutations(task).items():
                with self.subTest(task=task.id, mutation=name):
                    self.assertFalse(check(task, state)["passed"])

    def test_a_run_that_changed_nothing_passes_only_a_stop_task(self):
        for task in self.tasks:
            with self.subTest(task=task.id):
                self.assertIs(check(task, nothing_state(task))["passed"], task.decision == "stop")

    def test_passed_is_exactly_every_fact_present(self):
        for task in self.tasks:
            for state in [exact_state(task), nothing_state(task), *mutations(task).values()]:
                got = check(task, state)
                self.assertTrue(set(got["facts"].values()) <= {"present", "missing", "wrong"})
                self.assertIs(got["passed"], all(v == "present" for v in got["facts"].values()))

    def test_a_refusal_with_no_file_still_rejects_a_pull_request_and_a_secret(self):
        """Review focus: the refuse tasks expect no file and no pull request."""
        task = next(t for t in self.tasks if t.decision == "refuse" and t.expect["pr"] == "none")
        planted = mutations(task)
        self.assertIn("a pull request", planted)
        self.assertIn("a secret in the comment", planted)
        for name in ("a pull request", "a secret in the comment"):
            self.assertFalse(check(task, planted[name])["passed"], name)


class PassMetricTests(unittest.TestCase):
    """Part B, task 2: slide 10's counting form."""

    def test_slide_10_eight_runs_six_passes(self):
        self.assertAlmostEqual(pass_at_k(8, 6, 2), 0.9643, places=3)
        self.assertAlmostEqual(pass_hat_k(8, 6, 2), 0.5357, places=3)
        self.assertAlmostEqual(pass_hat_k(8, 6, 4), 0.2143, places=3)

    def test_pass_hat_k_is_not_pass_at_one_to_the_k(self):
        """Slide 10's warning: the shortcut is biased, so the two must differ."""
        self.assertNotAlmostEqual(pass_hat_k(8, 6, 2), (6 / 8) ** 2, places=3)


class SpreadAndIntervalTests(unittest.TestCase):
    """Part B, task 3: slides 17 to 20."""

    OLD = [61.0, 63.5, 59.5, 62.0, 64.5, 61.5, 62.5, 60.5, 63.0, 62.0]
    NEW = [63.5, 65.0, 62.5, 66.0, 64.5, 67.5, 65.0, 64.0, 66.5, 65.5]

    def test_slide_18_ten_sweeps_of_each_version(self):
        self.assertAlmostEqual(sum(self.OLD) / 10, 62.0, places=2)
        self.assertAlmostEqual(sum(self.NEW) / 10, 65.0, places=2)
        self.assertAlmostEqual(spread(self.OLD), 1.47, places=2)
        self.assertAlmostEqual(spread(self.NEW), 1.47, places=2)
        self.assertAlmostEqual(interval(self.NEW, self.OLD)[0], 3.0, places=2)

    def test_slide_19_and_20_margins(self):
        tight = margin(1.5, 10, 1.5, 10)
        self.assertAlmostEqual(tight, 1.31, places=2)
        self.assertAlmostEqual(3.0 - tight, 1.69, places=2)
        self.assertAlmostEqual(3.0 + tight, 4.31, places=2)
        wide = margin(6.0, 10, 6.0, 10)
        self.assertAlmostEqual(3.0 - wide, -2.3, places=1)
        self.assertAlmostEqual(3.0 + wide, 8.3, places=1)

    def test_a_single_sweep_has_no_spread(self):
        self.assertEqual(spread([42.0]), 0.0)
        self.assertEqual(spread([]), 0.0)

    def test_identical_sweeps_size_the_comparison_at_one(self):
        """Review focus: three equal sweeps give s = 0, which must not raise."""
        self.assertEqual(spread([2.0, 2.0, 2.0]), 0.0)
        self.assertEqual(sweeps_needed(0.0, 0.0, 0.1111), 1)


class TrajectoryMetricTests(unittest.TestCase):
    """Part B, task 4: slide 27's trace, counted."""

    def test_slide_27_trace(self):
        task = load_task(ROOT / "fixtures" / "traces7" / "s27.task.yaml")
        got = metrics(read_trace(ROOT / "fixtures" / "traces7" / "s27.jsonl"), task)
        self.assertEqual(got["step_count"], 3)
        self.assertAlmostEqual(got["precision"], 0.8)
        self.assertAlmostEqual(got["recall"], 1.0)
        self.assertEqual(got["repeats"], 1)
        self.assertEqual(got["orphans"], 1)
        self.assertFalse(got["no_tools"])

    def test_a_run_that_called_no_tool(self):
        """Review focus: slide 28's largest single kind of failure must not crash."""
        task = load_task(GOLDEN / "g01.yaml")
        lines = [{"type": "run_start", "run_id": "x"},
                 {"type": "run_end", "totals": {"cost_usd": 0.5}, "elapsed_s": 2.0}]
        got = metrics(lines, task)
        self.assertTrue(got["no_tools"])
        self.assertIsNone(got["precision"])
        self.assertEqual(got["recall"], 0.0)
        self.assertEqual(got["repeats"], 0)
        self.assertEqual(got["orphans"], 0)
        self.assertEqual(got["step_count"], -task.reference["calls"])
        self.assertAlmostEqual(got["cost_usd"], 0.5)
        self.assertAlmostEqual(got["latency_s"], 2.0)


class VerdictTests(unittest.TestCase):
    """Part C, task 5: the verdict follows from the bar, never from the average."""

    def test_holds_only_when_the_low_end_clears_the_bar(self):
        self.assertEqual(verdict_for(0.2, 1.4, 0.0, [0.4, 0.1], -0.5), "holds")
        # The average is well above the bar, but the interval's low end is not.
        self.assertEqual(verdict_for(-0.3, 2.1, 0.0, [0.4, 0.1], -0.5), "cannot_settle")

    def test_a_stratum_that_got_worse_overrules_a_win_on_the_average(self):
        self.assertEqual(verdict_for(0.2, 1.4, 0.0, [0.9, -0.8], -0.5), "cannot_settle")

    def test_fails_when_the_high_end_is_below_the_bar(self):
        self.assertEqual(verdict_for(-2.0, -0.4, 0.0, [-1.0], -0.5), "fails")

    def test_exactly_on_the_bar_does_not_hold(self):
        """Slide 20: the low end must clear the bar, not touch it."""
        self.assertEqual(verdict_for(0.0, 1.0, 0.0, [0.1], -0.5), "cannot_settle")


if __name__ == "__main__":
    unittest.main()
