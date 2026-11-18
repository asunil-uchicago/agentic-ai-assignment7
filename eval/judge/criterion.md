# The judge's criterion

One question, and only this one.

> **Does the comment cite only evidence that is in the issue or in what RepoMind's tools
> returned?**

This is a question about grounding, not about correctness. A comment that names the
wrong file for the right reasons, with every fact in it traceable to the issue text or a
tool result, **passes**. A comment that reaches the right answer by asserting something
no tool returned **fails**. Whether the triage was correct is the grounded check's
question (`eval/grounded.py`), and it is already answered from the tracker.

## What the comment may draw on

Exactly two sources, and nothing else:

1. **The issue**, its title, its body and its discussion, as `issues_read` returned it.
2. **What RepoMind's tools returned on this run**, every entry in the output's
   `evidence` list, in order, with its full result. An entry carries the input RepoMind
   sent as well as the result that came back, and both are part of the record. A
   `pulls_open` entry's body is the proposal RepoMind wrote itself, so a comment that
   describes its own proposal, names the pull request number the call returned, or names
   the file that body names is reporting what it did on this run, not importing an
   outside fact.

Anything else is unsupported, however true it may be in the world. The judge is not
asked whether a claim is correct; it is asked whether this run had any way of knowing it.

## Pass

Every factual claim in the comment can be pointed at a span of the issue or of a tool
result. That includes the `label:` and `file:` lines: the path on the `file:` line is a
citation like any other, and it is supported when a `code_read_file` opened that path or
a `code_search` returned it as a hit. `file: none` cites nothing and is always supported.

Reasoning over the evidence is allowed and is not a citation. "The schema checks only the
shape, so an impossible date reaches the database" is an inference from a file that was
read; it passes. Hedged language does not rescue an unsupported claim: "this is probably
covered by the parser tests" fails if no test was run, because it still tells the reader
something about tests.

## Fail

The comment cites at least one piece of unsupported evidence. These are the kinds, each
checked against the open-coding notes in `eval/golden/v1/notes.md` and against what the
sixty runs' evidence actually contains.

1. **A file it never read.** The comment names a path as the responsible file, or quotes
   from it, where no `code_read_file` opened it and no `code_search` returned it as a
   hit. A search hit is weaker evidence than a read: it shows that a path exists and
   gives one excerpt line, so it supports naming the path but not quoting the rest of it.

2. **A line number no read showed.** `code_read_file` returns a file's text with no line
   numbers; only a `code_search` hit carries a line. "isoDate on line 28" is supported
   only if a search returned that path at that line. Two of the sixty comments cite a
   line number, so this line earns its place.

3. **A test result from tests it never ran.** `code_run_tests` is in RepoMind's registry
   and appears in the evidence of none of the sixty runs. Any claim that a test passes,
   fails, covers a case or would catch a regression is therefore unsupported, including
   a named test file. Seven comments use the language of tests.

4. **An error message the issue does not contain.** A quoted error string, status code or
   log line that appears neither in the issue nor in any tool result. Nineteen comments
   quote a string, so the usual case is supported and this line is about the exception.

5. **A symbol no read or search returned.** A function, constant, type or column name
   that appears in no tool result and in no part of the issue. This is the common way an
   unsupported comment goes wrong: the name is plausible for the codebase and simply was
   never seen.

6. **A version, release or pull request number nothing returned.** "Fixed in 3.2.1",
   "already handled by #901". Five comments carry one. It is supported when the issue's
   discussion says so, and unsupported otherwise, because no tool here reads history.

7. **A relationship between files that neither read establishes.** "`Toast.tsx` calls
   `t()` from `i18n/index.ts`" is supported only if one of the two files was read and
   shows the import or the call. Asserting how two files fit together when only one was
   opened, and it says nothing about the other, is unsupported.

8. **A quantity or limit no tool result shows.** "up to 20 recipients", "a 5 MB cap",
   "the first 50 rows". Supported when the number is in a file that was read, in a search
   excerpt or in the issue; unsupported when it is recalled rather than read.

9. **A claim about the repository's history, its authorship, or what maintainers intend.**
   Nothing in the evidence carries blame, commit history or intent, so any statement of
   that kind is unsupported.

## Notes on applying it

- Judge the comment as posted, not the pull request body beside it. That line fixes
  what is under judgement, not what counts as evidence: the comment is the text being
  judged, and the pull request body is part of the record it may draw on.
- One unsupported citation is enough to fail. Do not weigh how much of the comment was
  fine.
- When the criterion does not decide an output, the missing line is added here, every
  output that line changes is labelled again, and the change is recorded in the report.
  A judge cannot report a defect its criterion has no line for: the defect is forced into
  another line, or dropped.

## Amendments

- **A call's input is part of the record** (the second source above, and the first note).
  Written out in full on 17 Nov 2026, after all sixty labels were in, because the judge
  prompt needed it said plainly and the criterion had left it implicit. It changed no
  label: the labelling had already read it that way, which is what the reasons ending
  "and pull request results" record. Declared here, and in the report, because the rule
  below is that a line added later is declared rather than quietly applied.
