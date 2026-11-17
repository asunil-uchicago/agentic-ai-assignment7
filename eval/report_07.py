"""Assignment 7: build reports/LAB_07.json from the artefacts (checks/FORMATS.md, 15.8).

    python -m eval.report_07             # write reports/LAB_07.json
    python -m eval.report_07 --print     # show it without writing

Every number here is computed from the golden set, results/A.jsonl and results/B.jsonl,
the traces, the tracker and the judge's verdict files. None is typed in. The checker
recomputes the same numbers its own way, so anything entered by hand would be a second
source of truth that could drift from the first.

A section whose inputs do not exist yet is left as the template has it, so this can be
run at any point and will fill in what it can.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
from pathlib import Path

import yaml

from harness import ROOT
from harness.formats import STRATA
from harness.tasks import load_tasks, read_subset

from eval import failures as failure_module
from eval.stats import interval, over_tasks, pass_at_k, pass_hat_k, spread

REPORT = ROOT / "reports" / "LAB_07.json"
GOLDEN = ROOT / "eval" / "golden" / "v1"
THRESHOLD = ROOT / "eval" / "thresholds" / "claim.yaml"
SUBSET = ROOT / "eval" / "subsets" / "claim.txt"
VERDICTS = ROOT / "eval" / "judge" / "verdicts"
LABELS = ROOT / "eval" / "labels" / "labels.csv"
SPLIT = ROOT / "eval" / "labels" / "split.yaml"


def mean(values) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


# -- Part A ----------------------------------------------------------------------------

def verdict_for(low: float, high: float, bar: float, stratum_gains: list[float], floor: float) -> str:
    """Slide 20's rule, applied to the committed bar (section 15.6).

    **holds** when the interval's low end is above the bar and no stratum's gain is below
    the group floor; **fails** when its high end is below the bar; **cannot_settle**
    otherwise. The average never decides: the interval's low end does, and a stratum that
    got worse overrules a win on the average.
    """
    if low > bar and all(gain >= floor for gain in stratum_gains):
        return "holds"
    if high < bar:
        return "fails"
    return "cannot_settle"


def golden_block() -> dict:
    tasks = load_tasks(GOLDEN / "tasks")
    strata = {s: sum(t.stratum == s for t in tasks) for s in STRATA}
    manifest = yaml.safe_load((GOLDEN / "manifest.yaml").read_text(encoding="utf-8"))
    return {"version": manifest["version"], "tasks": len(tasks), "strata": strata,
            "decisions": {d: sum(t.decision == d for t in tasks) for d in ("act", "refuse", "stop")},
            "thinnest": min(strata, key=lambda s: (strata[s], s))}


# -- Parts B and C ----------------------------------------------------------------------

class Arms:
    """Both arms' result lines, grouped the way slide 18 compares them."""

    def __init__(self, threshold: Path = THRESHOLD, prefix: str = ""):
        """`prefix` is "scripted_" to read the free rehearsal's results instead of the
        real ones, so the same code can be exercised before a token is spent."""
        self.spec = yaml.safe_load(threshold.read_text(encoding="utf-8")) if threshold.exists() else {}
        self.subset = read_subset(SUBSET) if SUBSET.exists() else []
        self.stratum_of = {t.id: t.stratum for t in load_tasks(GOLDEN / "tasks")}
        self.lines = {arm: jsonl(ROOT / "results" / f"{prefix}{arm}.jsonl") for arm in ("A", "B")}
        self.k = int(self.spec.get("k") or 1)

    @property
    def ready(self) -> bool:
        return all(len(self.lines[a]) >= 2 for a in ("A", "B")) and bool(self.spec)

    def sweep_values(self, arm: str, tasks: set[str] | None = None, score: bool = False) -> list[float]:
        """One value a sweep: the share of its tasks passed, in points, or the measure's
        mean over the sweep's runs (section 15.4)."""
        by_sweep: dict = collections.defaultdict(list)
        for line in self.lines[arm]:
            if tasks is None or line["task"] in tasks:
                by_sweep[line["sweep"]].append(line)
        out = []
        for sweep in sorted(s for s in by_sweep if s is not None):
            runs = by_sweep[sweep]
            out.append(100.0 * sum(bool(r["passed"]) for r in runs) / len(runs) if score
                       else mean(r["measure"] for r in runs))
        return out

    def _counts(self, lines: list[dict]) -> dict[str, tuple[int, int]]:
        counts: dict[str, tuple[int, int]] = {}
        for line in lines:
            n, c = counts.get(line["task"], (0, 0))
            counts[line["task"]] = (n + 1, c + bool(line["passed"]))
        return counts

    def _pass_metrics(self, lines: list[dict]) -> tuple[float | None, float | None]:
        counts = self._counts(lines)
        if not counts or any(n < self.k for n, _ in counts.values()):
            return None, None
        return over_tasks(counts, self.k)

    def arm_block(self, arm: str) -> dict:
        lines = self.lines[arm]
        measure, score = self.sweep_values(arm), self.sweep_values(arm, score=True)
        at_k, hat_k = self._pass_metrics(lines)
        present = sum(r["facts"]["present"] for r in lines)
        total = sum(r["facts"]["total"] for r in lines)
        spec = self.spec.get(f"arm_{arm.lower()}") or {}
        return {"way": spec.get("way"), "switches": spec.get("switches") or {}, "runs": len(lines),
                "measure": {"mean": mean(measure), "sd": spread(measure)},
                "score": {"mean": mean(score), "sd": spread(score)},
                "pass_at_k": at_k, "pass_hat_k": hat_k,
                "facts_share": present / total if total else None,
                "cost_per_run_usd": mean(r["cost_usd"] for r in lines),
                "no_tools": sum(1 for r in lines if r["metrics"]["no_tools"]),
                "by_stratum": self.stratum_block(arm)}

    def stratum_block(self, arm: str) -> dict:
        out = {}
        for stratum in STRATA:
            tasks = {t for t in self.subset if self.stratum_of.get(t) == stratum}
            lines = [r for r in self.lines[arm] if r["task"] in tasks]
            if not lines:
                continue
            at_k, hat_k = self._pass_metrics(lines)
            out[stratum] = {"runs": len(lines),
                            "measure": mean(self.sweep_values(arm, tasks)),
                            "score": mean(self.sweep_values(arm, tasks, score=True)),
                            "pass_at_k": at_k, "pass_hat_k": hat_k}
        return out

    def signed(self, a_values: list[float], b_values: list[float]) -> tuple[float, float, float]:
        """The gain, signed as the claim signs it, with its 95% interval."""
        if str(self.spec.get("gain", "")).replace(" ", "") == "B-A":
            return interval(b_values, a_values)
        return interval(a_values, b_values)

    def claim_block(self) -> dict:
        difference, low, high = self.signed(self.sweep_values("A"), self.sweep_values("B"))
        by_stratum = {}
        for stratum in STRATA:
            tasks = {t for t in self.subset if self.stratum_of.get(t) == stratum}
            a, b = self.sweep_values("A", tasks), self.sweep_values("B", tasks)
            if len(a) >= 2 and len(b) >= 2:
                d, lo, hi = self.signed(a, b)
                by_stratum[stratum] = {"difference": d, "interval": [lo, hi]}
        bar, floor = self.spec.get("bar"), self.spec.get("group_floor")
        verdict = verdict_for(low, high, bar, [v["difference"] for v in by_stratum.values()], floor)
        return {"claim": self.spec.get("claim"), "measure": self.spec.get("measure"),
                "gain": self.spec.get("gain"), "k": self.k, "sweeps": self.spec.get("sweeps"),
                "s_a": self.spec.get("s_a"), "s_b": self.spec.get("s_b"),
                "delta": self.spec.get("delta"), "n_needed": self.spec.get("n_needed"),
                "price_usd": self.spec.get("price_usd"),
                "difference": difference, "interval": [low, high],
                "by_stratum": by_stratum, "verdict": verdict}


# -- Part D ------------------------------------------------------------------------------

def rates_of(verdicts: dict[str, str], labels: dict[str, str]) -> tuple[float, float]:
    from eval.judge import rates
    return rates(verdicts, labels)


def judge_block() -> dict | None:
    """The judge's numbers, from the verdict files and the test labels only."""
    from eval.judge import CoinJudge, bootstrap, correct

    runs = [{row["id"]: row for row in jsonl(VERDICTS / f"test_{k}.jsonl")} for k in (1, 2, 3)]
    if not all(runs) or not SPLIT.exists() or not LABELS.exists():
        return None
    split = yaml.safe_load(SPLIT.read_text(encoding="utf-8"))
    with LABELS.open(newline="", encoding="utf-8") as fh:
        labels = {r["id"].strip(): r["label"].strip().lower() for r in csv.DictReader(fh)}

    test = list(split["test"])
    on_test = {i: labels[i] for i in test}
    first = {i: runs[0][i]["answer"] for i in test}
    tpr, tnr = rates_of(first, on_test)

    recorded = jsonl(VERDICTS / "recorded.jsonl")
    p = mean(1.0 if v["answer"] == "pass" else 0.0 for v in recorded) if recorded else None

    coin, corrected, bounds = False, None, None
    if p is not None:
        try:
            corrected = correct(p, tpr, tnr)
            bounds = list(bootstrap(first, on_test, p))
        except CoinJudge:
            coin = True

    flips = [i for i in test if len({r[i]["answer"] for r in runs}) > 1]
    majority = {i: ("pass" if sum(r[i]["answer"] == "pass" for r in runs) >= 2 else "fail") for i in test}
    m_tpr, m_tnr = rates_of(majority, on_test)

    versions = jsonl(VERDICTS / "versions.jsonl")
    moved = {v["id"] for v in versions if v["answer"] != first.get(v["id"])}

    system_of = {p.stem: json.loads(p.read_text(encoding="utf-8"))["system"]
                 for p in sorted((ROOT / "fixtures" / "judge" / "outputs").glob("*.json"))}
    by_system = {}
    for system in sorted({s for s in system_of.values() if s}):
        mine = {i: on_test[i] for i in test if system_of.get(i) == system}
        s_tpr, s_tnr = rates_of(first, mine)
        by_system[system] = {"tpr": s_tpr, "tnr": s_tnr}

    model = next((r.get("model") for r in runs[0].values() if r.get("model")), None)
    return {"split": {name: len(split[name]) for name in ("examples", "tuning", "test")},
            "model": model, "tpr": tpr, "tnr": tnr, "p": p, "corrected": corrected,
            "interval": bounds, "coin": coin,
            "flip_rate": len(flips) / len(test) if test else None,
            "majority": {"tpr": m_tpr, "tnr": m_tnr,
                         "kept": (m_tpr + m_tnr) > (tpr + tnr)},
            "moved_share": len(moved) / len(test) if test else None,
            "by_system": by_system}


# -- putting it together -------------------------------------------------------------------

def build() -> dict:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    report["golden"] = golden_block()

    arms = Arms()
    if arms.ready:
        report["claim"] = arms.claim_block()
        report["arms"] = {a: arms.arm_block(a) for a in ("A", "B")}
        entries = failure_module.failures()
        report["failures"] = [{k: v for k, v in f.items() if not k.startswith("_")} for f in entries]
        report["grid"] = failure_module.grid(entries)

    judge = judge_block()
    if judge is not None:
        report["judge"] = judge
    return report


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--print", action="store_true", dest="show", help="show it without writing")
    a = p.parse_args(argv)
    report = build()
    text = json.dumps(report, indent=2) + "\n"
    if a.show:
        print(text)
        return 0
    REPORT.write_text(text, encoding="utf-8")
    done = [name for name in ("claim", "judge") if report.get(name, {}).get("verdict" if name == "claim" else "tpr")]
    print(f"wrote {REPORT.relative_to(ROOT)}: golden filled"
          + (f", {' and '.join(done)} filled" if done else ", claim and judge still waiting on their inputs"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
