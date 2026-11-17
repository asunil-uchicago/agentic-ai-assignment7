# Assignment 7 · The evaluation harness, and a judge you have checked

Model: OpenAI `gpt-4o-mini`, the same for every run and for the judge.

## Part A · A golden set from traces

**The kinds of failure** you found by reading the recorded runs (slide 12), until no new kind appeared.

Twenty-five of the sixty runs went wrong. Each is counted once, under the **first** fault:
a run that reads the wrong file and then writes a comment about it has one fault, at the
read. The full notes, one per run, are in `eval/golden/v1/notes.md`.

| Kind of failure | Runs | One run that shows it, and its first wrong step |
|---|---|---|
| A. Turn limit reached with nothing written | 5 | `agent-issue-4601-s01-425ff8`, first wrong step `code_read_file(src/ingest/parser.ts)`: the fourth and last turn, spent reading instead of writing |
| B. Turn limit reached after the label and the pull request, before the comment | 3 | `agent-issue-4603-s01-fad434`, first wrong step `pulls_open`: the last turn available, leaving none for `issues_comment` |
| C. Searched, never read, and wrote only the comment | 5 | `workflow-issue-4615-s01-f75af0`, first wrong step `issues_comment`: reached after three searches with no `code_read_file` |
| D. Answered from the issue text alone | 6 | `direct-issue-4604-s01-0f6301`, first wrong step `issues_comment`: the second and last call, with no search and no read before it |
| E. Acted on an issue whose right move was to change nothing | 4 | `planned-issue-4613-s01-092041`, first wrong step `issues_label`: applied to an issue already fixed in release 3.2.1 |
| F. Took the file the reporter blamed | 1 | `planned-issue-4633-s01-a5f973`, first wrong step `code_read_file(src/ingest/dedupe.ts)`: taken as the answer, where #973 fixed `src/ingest/worker.ts` and recorded dedupe.ts as correct |
| G. Treated a question as a defect | 1 | `agent-issue-4604-s01-bab837`, first wrong step `issues_label(bug)`: on a question the maintainers answered by design |

- **Runs read, and when no new kind appeared:** all sixty, not the forty asked for. Read in
  run-id order, the last new kind (C) appeared at run 55 of 60. That number is an artefact
  of the ordering, not of the corpus: run ids sort by way, so all six `workflow` runs sit
  at the end and their shared kind could not appear earlier. Within a way, saturation came
  quickly: the 28 `agent` runs produced their last new kind at their 20th, the six `direct`
  runs produced one kind between them and nothing new after the first, and the `planned`
  runs added F and G by their sixteenth. Reading one more run of a way already seen would
  not have added a kind.

  Kinds A to D turn out to be properties of a **way**, not of an issue: every `direct` run
  shows D and every `workflow` run shows C or E, whatever issue it is handed. Kinds E, F
  and G are properties of the **issue**. Those three are what the golden set has to carry,
  because they are the ones a change to RepoMind could actually move.

**How you chose the tasks** (slide 12's table): every kind of task, the failures, each path, no copies.

27 tasks from the 40 issues in `fixtures/issues/pool/`, chosen against four requirements at once.

*Every kind of failure, its issues, up to five:*

| Kind | Tasks carrying it |
|---|---|
| A | g01, g11, g19, g22 |
| B | g07, g08 |
| C | g04, g14, g26 |
| D | g03, g12, g20 |
| E | g09, g18, g27 |
| F | g22 |
| G | g03 |

*Every path:*

| Path | Tasks |
|---|---|
| An issue that needs a pull request | 19, among them g01, g02, g05, g16, g23 |
| A question with no file | g03, g04, g17, g20 |
| A documentation fix | g08, g15, g21 |
| A refusal | g04, g10, g15, g20, g26 |
| Change nothing at all | g09, g13, g18, g27 |

*Copies left out.* Thirteen pool issues are not in the set. Twelve are second copies of a
case already covered: 4603, 4611 and 4630 are further amount-and-date parsing bugs behind
g01, g06 and g25; 4636 the maintainers themselves closed as a duplicate of 4601, which is
g01; and 4606, 4615, 4616, 4617, 4619, 4625, 4626 and 4637 are further routine single-file
bugs and features, where routine already holds nine. The thirteenth, 4607, is left out for
a different reason and it is worth saying so: it is an advertisement rather than an issue,
a genuinely distinct case, but it is still open, so its label would rest on my reading
alone where 26 of the 27 rest on a recorded resolution. A task whose right answer is only
my opinion is a weak test, and the adversarial stratum already holds eight.

*Where the labels come from.* 26 of the 27 cite the maintainers' own resolution in
`fixtures/closed_issues.yaml`, and four of those also cite the issue's discussion. One,
g26, cites my reading of the issue beside `src/api/health.ts`, because 4639 is still open.
No label is taken from what any run answered. That rule matters most on g03 and g22, where
a recorded run's answer and the maintainers' resolution disagree: had the label been read
off the run, neither task could ever fail.

| Stratum | Tasks | Decisions (act, refuse, stop) |
|---|---|---|
| routine | 9 | 9 act, 0 refuse, 0 stop |
| unusual | 6 | 6 act, 0 refuse, 0 stop |
| adversarial | 8 | 3 act, 5 refuse, 0 stop |
| should-not-act | 4 | 0 act, 0 refuse, 4 stop |
| **total** | **27** | **18 act, 5 refuse, 4 stop** |

- **The thinnest stratum, and the smallest fall it can show:** should-not-act, with four
  tasks. One task changing moves its score by 100/4 = **25 points**, so no fall smaller
  than 25 points can appear in it at all: a regression that breaks one run in five on
  those tasks is invisible there. That is the stratum where RepoMind's worst mistakes live
  (acting on an issue the maintainers closed untouched, kind E, four recorded runs), so it
  is the stratum whose thinness costs the most. Widening it means finding more issues the
  maintainers closed with no change, and the pool holds only one more, 4636, which is a
  duplicate.

  The grounded check was tested against the notes before anything else used it: on the 40
  recorded runs whose issue is in the set, every run the notes called wrong fails and
  every run they called right passes, with **zero disagreements**. A disagreement would
  have meant either the note or the check was wrong, and finding which is the point of
  running it.

## Part B · The harness

- **How a run becomes a line in `results/`, and what reads the end state:**
  `eval/results_07.py` takes the arm's finished runs from `runs/` (`finished_runs`, which
  keeps only runs that reached `run_end` and did not stop on quota or a rate limit, on a
  real model), drops any whose task is outside the pushed subset, and writes one line per
  run. For each: `eval.grounded.check_run` rebuilds the run's **end state from the
  tracker's database** and scores it against the task's label, giving `passed` and the
  facts count; `eval.metrics.metrics` counts the five trajectory metrics from the trace;
  the claim's measure is computed per section 15.4; and the tokens, cost and wall clock
  come from the run's last `run_end` line.

  Nothing in that path reads what the agent said. The comment says what RepoMind meant to
  do; the tracker says what it did. That separation is the only thing that catches a run
  which stops early and reports success, because nothing inside such a run disagrees with
  itself: `agent-issue-4603-s01-fad434` left a label and a pull request and no comment, and
  only a check from outside the run can see that the issue's author was told nothing.

- **One table from your Part C results, as the harness reports it (runs, spread, pass@k and pass^k with *k*):**

  *Waiting on Part C's runs.*

## Part C · Settle one claim

- The claim, its two arms, the measure and the sign of the gain:
- The first three sweeps: each arm's *s*, and the cost of one sweep:
- *δ*, the sweeps it needs, and the price (slide 55):
- The bar and the group rule, as committed, and the commit:

**The results**, from `results/`.

| Arm | Runs | Measure: mean (SD) | Score: mean (SD) | pass@k | pass^k | Facts right | Cost per run |
|---|---|---|---|---|---|---|---|
| A | | | | | | | |
| B | | | | | | | |

| Stratum | Gain | 95% interval |
|---|---|---|
| All tasks | | |
| routine | | |
| unusual | | |
| adversarial | | |
| should-not-act | | |

- The verdict, by your bar, and why:
- Cost beside the score (slide 54):
- Each part of your prediction that missed, and the run that shows why:

**Where the failed runs first went wrong** (slide 29), last good step down the side, first wrong step across.

```
```

- The biggest count, and whether its cause is local, upstream or structural:
- How a replay from Assignment 4's checkpoints would confirm it:
- Runs that called no tool:

## Part D · Validate a judge

- The criterion's lines, and what labelling added to them:
- The split, and when it was committed:
- The judge: its model and version, and its TPR and TNR on the test set:
- Its pass rate on the recorded runs, corrected, with its interval:
- Its flip rate, and whether a majority of three was kept:
- What moved on the reformatted and lengthened versions:
- Its rates on each system:
- What validating the judge still needs:

## AI assistance

Which tool, what it wrote, and what you checked. No assistant writes or suggests a label.
