# ARCHITECTURE.md · RepoMind on the seven layers

For each layer: what does this job, and where is it enforced. Cite code as a file
path and line number joined by a colon, inside backticks; a checker opens every
reference (`checks/FORMATS.md`, section 8). A layer held only by a sentence in a
prompt (any file under `prompts/`) is **EMPTY**, and so is a layer nothing does
yet. Status is one of: present, partial (say what is missing), or **EMPTY**. Each
assignment brings this file up to date.

What each layer is for (Lecture 1, slides 42 to 44):

- **Model**: reasoning, choosing tools, generating text.
- **Harness**: runs the loop, builds each prompt, trims old history.
- **Tools**: where the system acts on the world.
- **Memory & State**: what survives a step, a session, a restart.
- **Control & Policy**: what the system may do, and when it must ask.
- **Observability**: a step-by-step record of what it did.
- **Evaluation**: measuring quality, before and after release.

The table below is RepoMind as Assignment 5 leaves it: its working solution.

| Layer | What does this job | Where it is enforced | Status |
|---|---|---|---|
| Model | The configured model, called only through the metered client | `harness/client.py:150` | present |
| Harness | The loop, with three bounds checked in code; a plan validated before it runs, and an executor that runs only the plan's steps; the client drains the user's messages before every call | `agent/loop.py:38`, `ways/planned.py:327`, `ways/planned.py:488`, `ways/planned.py:180` | present |
| Tools | Ten namespaced tools behind one registry: every call checked at the boundary before it runs; every write keyed by the harness, checked before each attempt and read back after a timeout; every attempt in the call record | `tools/__init__.py:170`, `tools/__init__.py:260`, `tools/__init__.py:269`, `tools/__init__.py:286`, `tools/__init__.py:325` | present |
| Memory & State | A checkpoint after each file read and before each write, sync, and a resume from the last one; a store of dated records with their origin, read before the first search and written once at the end of a run | `ways/planned.py:387`, `ways/planned.py:400`, `ways/planned.py:263`, `ways/planned.py:283`, `state/checkpointer.py:55`, `state/store.py:96` | present |
| Control & Policy | The autonomy policy in three columns, enforced by a pre-call hook outside the model: a stop first, prohibited before everything, a user's boundary kept as a rule, the disclosure line, and the reviewer asked for a gated call, with no answer never a yes; an escalation on a named signal that holds; a stop with a live notification; rollback by the remote's compensations | `tools/__init__.py:147`, `policy/hook.py:52`, `policy/hook.py:130`, `policy/hook.py:142`, `policy/hook.py:145`, `policy/hook.py:154`, `policy/hook.py:174`, `policy/boundary.py:33`, `ways/planned.py:209`, `ways/planned.py:460`, `ways/planned.py:546`, `policy/escalation.py:49`, `bin/rollback:24` | partial: the approvals still decay, as Lecture 5's Section B predicts, and nothing measures harm prevented |
| Observability | One trace line per model call and per tool call, and the plan as data before it runs; every refusal in the hook log, every decision in the decisions log, every write in the remote's log | `agent/loop.py:50`, `ways/planned.py:219`, `policy/hook.py:183` | partial: traces and logs, no alerts |
| Evaluation | A versioned golden set of 27 labelled tasks drawn from RepoMind's own history; a grounded check that scores a run from the tracker's end state against the task's label, never from the agent's words; both pass metrics, the spread, the interval and the sizing arithmetic; five trajectory metrics counted from the trace; one result line per run; the first wrong step of every failed run; and a model judge whose two error rates are measured against sixty hand labels before its rate is used | `eval/grounded.py:113`, `eval/grounded.py:146`, `eval/stats.py:21`, `eval/stats.py:27`, `eval/stats.py:60`, `eval/stats.py:71`, `eval/metrics.py:86`, `eval/results_07.py:114`, `eval/failures.py:50`, `eval/judge.py:1`, `eval/report_07.py:225` | partial: offline only, and the judge is validated on one criterion |

**Empty layers: 0 of 7**, and three are partial.

## The Evaluation layer, after Assignment 7

Assignment 7 is the first time this layer measures rather than asserts. What it holds:

| Piece | What it does | Where |
|---|---|---|
| The golden set | 27 tasks over four strata, each with the decision RepoMind's design expects, the end state that decision leaves, how the label is known, and the calls a good run makes. Drawn from the 60 recorded runs and Ledgerline's closed-issue history, never from what a run answered | `eval/golden/v1/manifest.yaml`, `eval/golden/v1/tasks/`, `eval/golden/v1/notes.md` |
| The grounded check | Eight facts per task, read from the end state: the comment, the labels, the pull request, nothing closed, nothing merged, nothing pushed, nothing written on another issue, and no secret in anything written. A run passes only with all eight present | `eval/grounded.py:113` |
| The statistics | pass@k and pass^k from one count of passes, the SD over sweep values, the margin and the 95% interval of a difference, and Activity 2's sizing arithmetic | `eval/stats.py:21`, `eval/stats.py:27`, `eval/stats.py:43`, `eval/stats.py:53`, `eval/stats.py:60`, `eval/stats.py:71` |
| The trajectory metrics | Step count, tool precision and recall, repeats, orphan reads, whether any tool was called at all, cost and latency, all by counting the trace | `eval/metrics.py:86` |
| The result line | One line per finished run: the grounded verdict, its facts, the claim's measure, the tokens, the cost, the wall clock and the five metrics | `eval/results_07.py:114` |
| First failures | The first wrong step of every failed run, by a stated rule rather than a judgement, and the grid counted from the same list | `eval/failures.py:50`, `eval/failures.py:136` |
| The judge | One criterion, a frozen prompt, verdicts through a metered session, TPR and TNR on held-out labels, a corrected rate with a bootstrap interval, and a guard that refuses to correct a judge no better than a coin | `eval/judge/criterion.md`, `prompts/judge.md`, `eval/judge.py:1` |
| The report | Every number in `reports/LAB_07.json` computed from the artefacts, so the checker's recomputation and the report cannot drift | `eval/report_07.py:225` |

What the layer still does not do: it runs offline, after the fact, never in front of a
release; the judge is validated on one criterion, so a comment can be well grounded and
still unhelpful; and the thinnest stratum holds four tasks, so nothing smaller than a
25-point fall can register there.
