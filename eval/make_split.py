"""Assignment 7, Part D, task 3: split the sixty labelled outputs, blind.

    python -m eval.make_split            # writes eval/labels/split.yaml
    python -m eval.make_split --check    # report on an existing split, write nothing

Three sets: examples for the judge's prompt, tuning to refine it against, and test, held
out. Sizes 9 / 26 / 25, inside section 15.9's 10-20% / 40-45% / 40-45%.

The split is balanced across both systems and both verdicts, so no set is all passes or
all fails: a test set with no fails leaves TNR undefined, and a prompt tuned on one
system's outputs would be measured on the other's. Balancing needs the labels, so this
script reads them.

It therefore prints **aggregate counts only**: how many of each set, and how many passes
and fails in each. It never prints an id beside a verdict, and never prints the test set
with labels attached. Whoever writes the judge's prompt must not learn how a test item
is labelled, or TPR and TNR stop measuring the judge and start measuring the tuning
(slide 42).
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import random
from pathlib import Path

from harness import ROOT

OUTPUTS = ROOT / "fixtures" / "judge" / "outputs"
LABELS = ROOT / "eval" / "labels" / "labels.csv"
SPLIT = ROOT / "eval" / "labels" / "split.yaml"
SIZES = {"examples": 9, "tuning": 26, "test": 25}
SEED = 7


def read_labels(path: Path = LABELS) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as fh:
        return {row["id"].strip(): row["label"].strip().lower() for row in csv.DictReader(fh) if row.get("id")}


def systems(where: Path = OUTPUTS) -> dict[str, str]:
    return {p.stem: json.loads(p.read_text(encoding="utf-8"))["system"] for p in sorted(where.glob("*.json"))}


def make_split(labels: dict[str, str], system_of: dict[str, str], seed: int = SEED) -> dict[str, list[str]]:
    """Deal the outputs into the three sets, balanced by system and by verdict.

    Each (system, label) group is shuffled with a fixed seed and dealt round-robin, so
    every set carries both models and both verdicts in roughly the corpus's proportions,
    and the same labels always give the same split.
    """
    rng = random.Random(seed)
    groups = collections.defaultdict(list)
    for out_id in sorted(labels):
        groups[(system_of.get(out_id), labels[out_id])].append(out_id)
    for members in groups.values():
        rng.shuffle(members)

    # Interleave the groups, one member at a time, so neighbours in the sequence come
    # from different systems and different verdicts. Dealing a group at a time instead
    # lets the smallest set fill entirely from one group.
    order = sorted(groups, key=lambda k: (-len(groups[k]), str(k)))
    sequence = [out_id for row in zip(*(groups[k] + [None] * (max(map(len, groups.values())) - len(groups[k]))
                                        for k in order))
                for out_id in row if out_id is not None]

    want = dict(SIZES)
    split: dict[str, list[str]] = {name: [] for name in SIZES}
    for out_id in sequence:
        # The set furthest from full *as a share of its own size*, so all three fill at
        # the same rate and the 9-item set draws from the whole sequence, not its tail.
        name = max(want, key=lambda n: ((want[n] - len(split[n])) / want[n], n))
        split[name].append(out_id)

    _repair(split, labels)
    return {name: sorted(ids) for name, ids in split.items()}


def _repair(split: dict[str, list[str]], labels: dict[str, str]) -> None:
    """Guarantee every set holds at least one pass and one fail, by swapping.

    Interleaving makes an all-one-verdict set unlikely, not impossible: a corpus that is
    almost all passes can still starve the 9-item set of a fail. A rate computed on such
    a set is undefined, so the guarantee is worth a swap rather than a warning.
    """
    for name, ids in split.items():
        for wanted in ("pass", "fail"):
            if any(labels[i] == wanted for i in ids):
                continue
            donor = next((d for d in split
                          if d != name and sum(labels[i] == wanted for i in split[d]) > 1), None)
            if donor is None:
                continue                      # the corpus itself has too few of this verdict
            give = next(i for i in split[donor] if labels[i] == wanted)
            take = next(i for i in ids if labels[i] != wanted)
            split[donor][split[donor].index(give)] = take
            ids[ids.index(take)] = give


def report(split: dict[str, list[str]], labels: dict[str, str], system_of: dict[str, str]) -> None:
    """Aggregate counts only: never an id beside its verdict."""
    print(f"{'set':<10} {'n':>3}  {'pass':>5} {'fail':>5}   by system")
    for name in ("examples", "tuning", "test"):
        ids = split[name]
        passes = sum(labels[i] == "pass" for i in ids)
        by = collections.Counter(system_of.get(i) for i in ids)
        print(f"{name:<10} {len(ids):>3}  {passes:>5} {len(ids) - passes:>5}   "
              + ", ".join(f"{s}: {n}" for s, n in sorted(by.items())))


def problems(split: dict[str, list[str]], labels: dict[str, str]) -> list[str]:
    flat = [i for ids in split.values() for i in ids]
    out = []
    if sorted(flat) != sorted(labels):
        out.append("the three sets are not disjoint, or do not cover every output once")
    for name, size in SIZES.items():
        if len(split[name]) != size:
            out.append(f"{name} holds {len(split[name])}, not {size}")
    for name, ids in split.items():
        kinds = {labels[i] for i in ids}
        if kinds != {"pass", "fail"}:
            out.append(f"{name} holds only {kinds}, so a rate computed on it is undefined")
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--check", action="store_true", help="report on the existing split, write nothing")
    p.add_argument("--seed", type=int, default=SEED)
    a = p.parse_args(argv)

    labels, system_of = read_labels(), systems()
    if len(labels) != len(system_of):
        raise SystemExit(f"{len(labels)} labels for {len(system_of)} outputs: label them all first "
                         "(python -m eval.label_tool)")

    if a.check:
        import yaml
        split = {k: list(v) for k, v in (yaml.safe_load(SPLIT.read_text(encoding="utf-8")) or {}).items()}
    else:
        split = make_split(labels, system_of, a.seed)

    for problem in problems(split, labels):
        print(f"PROBLEM: {problem}")
    report(split, labels, system_of)

    if not a.check:
        SPLIT.parent.mkdir(parents=True, exist_ok=True)
        SPLIT.write_text(
            "# Part D's split, made by eval/make_split.py with seed %d, balanced across both\n"
            "# systems and both verdicts. Committed before the judge: the prompt is written\n"
            "# against examples and tuning only, and no test label is read before it is frozen.\n"
            % a.seed
            + "".join(f"{name}: [{', '.join(split[name])}]\n" for name in ("examples", "tuning", "test")),
            encoding="utf-8")
        print(f"\nwrote {SPLIT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
