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

  | Arm | Runs | Measure: mean (SD) | pass@3 | pass^3 |
  |---|---|---|---|---|
  | A, examples on | 45 | 2.378 (0.390) | 0.111 | 0.011 |
  | B, examples off | 45 | 5.044 (0.435) | 0.211 | 0.044 |

  *k* is 3: with five sweeps a task has five runs, and three is the largest *k* that still
  leaves the counting form room to separate the arms. `pass^3` is computed as
  `C(c, 3) / C(n, 3)`, never as `pass@1` cubed, which slide 10 warns is biased.

## Part C · Settle one claim

- **The claim, its two arms, the measure and the sign of the gain:** the tool examples in
  the prompt earn their tokens. Arm A is `planned` with examples on, its default; arm B is
  `planned` with `TOOL_EXAMPLES=off`, nothing else changed. The measure is a run's wasted
  calls: every call whose outcome is `rejected`, `error` or `protocol`, plus every search
  whose result carries `"count": 0`. The gain is signed `B - A`, so a positive gain means
  arm B wasted more and the examples helped. Model `gpt-4o-mini`, served as the dated
  snapshot `gpt-4o-mini-2024-07-18`, read from the runs' `model_call` lines rather than the
  alias in `run_start`.

- **The first three sweeps: each arm's *s*, and the cost of one sweep:** *s*<sub>A</sub> 0.231,
  *s*<sub>B</sub> 0.570, over the nine tasks of `eval/subsets/claim.txt`. One sweep costs
  $0.0158 in arm A and $0.0132 in arm B.

- **δ, the sweeps it needs, and the price (slide 55):** δ is 0.5 wasted calls per task, the
  smallest gap worth turning the examples back on for. `sweeps_needed(0.231, 0.570, 0.5)`
  is 12, priced at 12 × 2 arms × $0.0145 a sweep, or $0.35. The protocol fixes five sweeps
  per arm, and five resolves a gap of 0.77. I ran twelve before noticing; those runs are in
  `runs/discarded/`, and they change nothing, since the difference over twelve sweeps is
  2.694 against 2.667 over five. Sizing for 0.5 turned out conservative by a wide margin:
  the gap that exists is 2.667, more than five times δ.

- **The bar and the group rule, as committed, and the commit:** the interval's low end must
  clear a bar of 0.0, and no stratum's gain may fall below a floor of -0.5, with *k* = 3.
  Committed in `cfa4653` at 2026-11-17T17:53:19, before any sweep-4 run started.

**The results**, from `results/`.

| Arm | Runs | Measure: mean (SD) | Score: mean (SD) | pass@3 | pass^3 | Facts right | Cost per run |
|---|---|---|---|---|---|---|---|
| A, examples on | 45 | 2.378 (0.390) | 6.67 (6.09) | 0.111 | 0.011 | 69.7% | $0.00177 |
| B, examples off | 45 | 5.044 (0.435) | 13.33 (9.30) | 0.211 | 0.044 | 70.6% | $0.00148 |

| Stratum | Gain | 95% interval |
|---|---|---|
| All tasks | +2.667 | [2.155, 3.178] |
| routine | +3.800 | [2.813, 4.787] |
| unusual | +2.100 | [0.932, 3.268] |
| adversarial | +1.100 | [-0.334, 2.534] |
| should-not-act | +3.100 | [1.714, 4.486] |

- **The verdict, by your bar, and why: holds.** The interval's low end, 2.155, is above the
  bar of 0.0, so the gap is not an artifact of which sweeps happened to run. Every stratum
  clears the floor of -0.5, the smallest being adversarial at +1.100. Note that
  adversarial's own interval, [-0.334, 2.534], crosses zero: the gap is real across the
  subset as a whole, and on adversarial tasks alone these ten runs cannot tell.

- **Cost beside the score (slide 54): the claim holds and acting on it would still be
  wrong.** Arm B wastes twice the calls and scores twice as well, 13.33 against 6.67, with
  pass@3 at 0.211 against 0.111. It is also cheaper per run, $0.00148 against $0.00177,
  because the examples are tokens in every prompt. Arm A left six runs that called no tool
  at all; arm B left none. So the examples buy tidier traces, not better triage, and the
  measure I chose cannot see the thing worth having. A claim can be settled and still be
  the wrong claim, which is the part of this that was worth learning.

- **Each part of your prediction that missed, and the run that shows why:** the arm was
  right, A, and the stratum was right, routine, at +3.800. The size missed: I committed 2.0
  and measured 2.667, and the interval [2.155, 3.178] excludes 2.0, so it missed low rather
  than merely being imprecise. `planned-g02-s04-847e73` shows why. Without the examples that
  run had `issues_read`, `issues_label` and `issues_comment` all rejected for malformed
  arguments, one `code_read_file` error and three empty searches: seven wasted calls in a
  two-step run. I had expected malformed arguments to cluster in the read tools, where the
  arguments are paths and queries. They hit the write tools just as hard, and that is what
  carried should-not-act to +3.100 when I expected that stratum to be modest.

**Where the failed runs first went wrong** (slide 29), last good step down the side, first wrong step across.

```
arm A, 42 failed runs                      arm B, 39 failed runs

last good        -> first wrong   count     last good        -> first wrong   count
code_search         code_read_file   18     issues_label        stop             20
issues_label        stop              9     code_search         code_read_file   11
code_read_file      issues_label      6     code_read_file      issues_label      5
start               stop              4     code_search         code_search       2
issues_label        pulls_open        3     issues_label        pulls_open        1
code_search         issues_label      1
issues_comment      stop              1
```

- **The biggest count, and whether its cause is local, upstream or structural:** arm B's
  `issues_label -> stop`, 20 of its 39 failures. The run labelled the issue and then ended
  without ever writing the comment the task needed. The cause is **upstream**, not local to
  the label step: nothing is wrong with the labelling call, and the run had a comment left
  to write. It had spent its turns on the wasted calls counted above, so the budget ran out
  before the last step of the plan. Arm A shows the same shape nine times instead of twenty,
  close to the ratio of wasted calls between the arms. The second count, arm A's
  `code_search -> code_read_file` at 18, is a different and genuinely local fault: the search
  returned hits and the run opened the wrong one.

- **How a replay from Assignment 4's checkpoints would confirm it:** resume each of the 20
  from its checkpoint immediately after `issues_label`, with the turn budget restored, and
  change nothing else. If they then write the comment, the fault was the budget and the
  wasted calls that drained it, which is the upstream reading. If they still stop, the fault
  is in the plan's own ordering, which puts the comment after the label, and the reading is
  structural instead. The same replay separates the two for arm A's nine.

- **Runs that called no tool:** six, all in arm A, on tasks g08, g14 and g18
  (`planned-g08-s01-e3803d`, `planned-g14-s02-b4173e`, `planned-g14-s03-f30fd5`,
  `planned-g14-s04-177981`, `planned-g18-s04-714301`, `planned-g18-s05-f264fa`). Arm B had
  none. Slide 28 calls this the largest single kind of failure. `eval/metrics.py` reports
  `precision` as null rather than zero for these, since a run that called nothing has no
  precision to report, and records `step_count` as the negative of the task's reference count.

## Part D · Validate a judge

- **The criterion's lines, and what labelling added to them:** nine kinds of unsupported
  citation, each written against what the sixty runs' evidence actually holds rather than
  against what a comment could go wrong about in principle. Labelling put 17 of the sixty
  in the fail column: a file never read 4 (`j04`, `j12`, `j41`, `j49`, the first two of
  them test files, which is kind 3 by another route), an error or log line the issue does
  not contain 4 (`j21`, `j23`, `j29`, `j37`), a line number no read showed 2 (`j02`,
  `j34`), a claim about history or intent 2 (`j40`, `j48`), and one each of a symbol
  nothing returned (`j59`), a relationship neither read establishes (`j03`) and a quantity
  nothing shows (`j46`). Two fit none of the nine. `j47` says `parseAmount` accepts a
  trailing minus where the file that was read handles only a leading minus and
  parentheses: the evidence contradicts that claim rather than failing to support it, and
  all nine kinds are about absence. `j55` says failed uploads are kept in the bucket's
  quarantine folder, a statement about what the system does in a case no file shown
  describes. Both were forced into the nearest existing line while labelling, which is
  exactly what the criterion's closing note predicts happens to a defect with no line of
  its own. Writing the two lines properly would mean labelling all sixty again, and the
  split is committed, so the only amendment made was the one that changes no label: a
  call's input is part of the record, which the labelling had already assumed and the
  judge prompt needed stated. It is declared in `eval/judge/criterion.md`.

- **The split, and when it was committed:** 9 examples, 26 tuning, 25 test, seeded at 7
  and balanced on both the verdict and the system that wrote the comment, so no set is one
  writer's work. Committed in `2a800cc` at 2026-11-17 21:02:22, before `eval/judge.py` and
  `prompts/judge.md` existed in the history at all; those went up in `48f5e04` at 23:28:44.
  That ordering is the entire guarantee, and it is why the test labels could not have
  shaped the prompt. The prompt was tuned against the 9 and the 26 only, across six
  versions and nine metered sessions in `runs/judge/`, and no test item was judged or read
  until the prompt was frozen and pushed.

- **The judge: its model and version, and its TPR and TNR on the test set:** `gpt-4o-mini`,
  served as the dated snapshot `gpt-4o-mini-2024-07-18`, read from the verdict lines rather
  than the alias. On run 1, TPR 0.526 and TNR 0.667, summing to 1.193. The coin guard
  refuses any judge whose rates sum within 0.1 of 1, so this clears the guard by 0.093 and
  nothing more. Runs 2 and 3, same prompt, same 25 items, sum to 1.412 and 1.465. The gap
  between those three says more about the spread than any one of them says about the judge.

- **Its pass rate on the recorded runs, corrected, with its interval:** 14 of the 20
  recorded agent runs that posted a comment were judged grounded, a raw rate of 0.700.
  Correcting it with `(p + TNR - 1) / (TPR + TNR - 1)` gives 1.90, which clips to 1.000.
  The bootstrap interval is [0.000, 1.000]: of 2000 resamples, 484 landed inside the coin
  band and were dropped, and most of the 1513 that survived clipped at one end or the
  other. The corrected figure is not a measurement. A denominator of 0.193 multiplies every
  error in the two rates by about five, and the interval is the honest report of that. This
  test set cannot bound the true grounded rate at all, and the right reading of 1.000 is
  "unknown", not "perfect".

- **Its flip rate, and whether a majority of three was kept:** 8 of the 25 test items
  changed verdict across the three runs, a flip rate of 0.32, listed by id in
  `eval/judge/for_a_person.txt`. A majority of three lifts TPR to 0.632 and TNR to 0.833,
  summing to 1.465 against run 1's 1.193, so it was kept. Three runs cost three times one
  and buy a judge that is meaningfully less bad. The same instability showed in tuning:
  two runs of the frozen prompt over the 35 tuning and example items returned identical
  TPR and TNR, which looked like stability until the per-item comparison showed 8 of 35
  had flipped and the flips had cancelled. Matching aggregates are not a steady judge.

- **What moved on the reformatted and lengthened versions:** 13 of the 25 moved, a share
  of 0.52, and the direction is the finding. The list version, the same content set as
  bullets, moved 6 and made the judge more lenient: 14 of 25 passed against run 1's 12. The
  long version moved 10 and made it stricter: 10 of 25 passed. The claims are identical in
  all three. A judge whose verdict changes on more than half the items when only the
  presentation changes is reading format, which is the one thing the criterion tells it to
  ignore.

- **Its rates on each system:** the two TNRs match exactly at 0.667, but TPR is 0.700 on
  the Haiku-written comments and 0.333 on the Sonnet-written ones. The judge fails two of
  every three grounded Sonnet comments. Sonnet's are the longer comments, which lines up
  with the long version being judged more harshly, so the likely mechanism is that the
  judge penalises length and length happens to track the writer. One overall TPR of 0.526
  would have hidden a bias large enough to change which system this evaluation recommends.

- **What validating the judge still needs:** three things, in order. First, more negatives.
  The sixty came out 43 pass to 17 fail, so the test set holds 6 fails and the whole of TNR
  rests on them; one verdict moves it by 0.167. The corpus needs labelling toward a
  balance, not toward whatever the runs produced. Second, a judge that does not read
  format: the 0.52 moved share says the next prompt should be tuned against the reformatted
  variants rather than the originals, so that invariance is what gets optimised instead of
  agreement on one presentation. Third, the two criterion lines that labelling exposed and
  the split then froze, contradiction and unshown behaviour. Those need writing down and
  all sixty labelling again against the fuller criterion, which makes a new corpus rather
  than a patch to this one. My own labelling is not clean either: tuning surfaced `j25`, an
  examples-set item I marked pass whose comment cites `docs/API.md`, a file no call opened.
  I left it as labelled, because relabelling after seeing the judge's output is how a
  held-out set stops being held out, and one slip in the nine I have since reread is a rate
  worth knowing when the labels are the ground truth. Until all three are done, the honest
  use of this judge is as a filter that flags comments for a person, not as a number in a
  report. Its own interval says the same.

## Two things I ran into on Windows

**The `fixtures/judge/` integrity flag.** I had not touched the fixtures, so I went
looking for the cause. `sha()` at `checks/check_07.py:135` folds
`str(f.relative_to(path))` into the hash, which gives `outputs\j01.json` here and
`outputs/j01.json` elsewhere. I rehashed the same bytes with `.as_posix()` and got the
expected `0920675979cd96a9` exactly, so the contents match the course copy and only the
separator differs. `fixtures/judge/` is the only pinned directory with a nested
subdirectory, which is why the two flat ones do not flag.

**The 4 points under "The maths".** The section told me 0 tests ran, which did not match
`python -m unittest tests.test_eval` passing 18. `checks/check_07.py:375` opens the
runner's stream with `open("/dev/null", "w")`, and that raises `FileNotFoundError` here
before the first test executes. I ran those same two lines with `os.devnull` and got 18
run, 0 failures, 0 errors.

## AI assistance

I used Gemini Web App and Claude Code to better understand the repository. I also used
Claude Code to help draft the prompts and report, and to diagnose the two Windows issues
described in the section above. I used GitHub Copilot autocompletion while coding and Claude
to debug any errors I had. I also made sure to manually verify any work done by AI. All 60
labels in `eval/labels/labels.csv` are mine, done manually.
