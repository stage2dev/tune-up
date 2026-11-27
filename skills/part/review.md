# Part review - detail

`<plugin>` = the absolute plugin folder already expanded in the commands of SKILL.md (never a `$` variable), `<S>` = the scratchpad, `<R>` = `<phase folder of the LOCAL plans_dir>/review-<X>`, one folder per Part next to progress (`mkdir -p` it first): a new session finds the findings there; it never goes to the PR. Type the commands in exactly this form, absolute paths, nothing after them: a heredoc, a redirection, a pipe, a glob or `~` makes the guard ask.

## Route and call

1. Names: `git diff --name-only --no-renames --no-ext-diff --ignore-submodules=none <base>..HEAD`. Patch and route:

```
git diff --no-renames --no-ext-diff --ignore-submodules=none <base>..HEAD > "<S>/diff-part.patch"
sh "<plugin>/scripts/py" scripts/guarda.py rota --part --files <names> --diff-file "<S>/diff-part.patch"
```

   Answer: `{"part":true,"risk","reviewers","models":{"<lens>":"<model>"},"effort":"high","lines","chunks","why"}`. An error counts as risk: call all three lenses (the error answer lists all three on opus). A base item: same commands over `<before item>..<item commit>`, without `--part`. `<base>` and every commit are hashes; an empty diff is never reviewed and never approved.
2. One call per reviewer of `reviewers` (never fewer), each on its model from `models` (a recheck: Model: sonnet; the lens's own model once that unit had a CRITICAL), high, ALL in ONE message, in the foreground (through the Workflow template they run inside call 2). Each gets: `git diff --no-ext-diff --ignore-submodules=none <base>..HEAD` (or its chunk's paths), criterion C, `PITFALLS TO READ`, the side skill paths the executor had (reference only: not to read unless needed to prove a finding; the repo convention wins) with any matched skill its `skills_read` missed, and the base items already reviewed with the commit of each.
3. `chunks` > 1: split by side (front, back) or by item group. EVERY path of the name list is in exactly ONE chunk; what is left goes to a `rest` chunk (the template builds it from `files`). Each chunk goes to EVERY reviewer of the route, with `git diff --stat <base>..HEAD` of the WHOLE Part. Add one reviewer-failures for the boundaries between chunks (for example front x back: contracts, field names, order of deploy). Labels, never repeated: `front`, `back`, `rest`, `boundary`; one chunk or none: `all`; a base item: `item-b1`.
4. DUPLICATION: HIGH only when the copies already diverge or must change together; otherwise MEDIUM.

## Saving an answer

The reviewer has no Write. Its final answer is the CRITICAL/HIGH list, a compact json block with ALL findings (`line` an integer or null), then the Verdict line, whose counts equal the json (about 25 lines). Save the WHOLE answer with the Write tool to `<S>/answer-<lens>-<chunk>-<round>.txt`, then:

```
sh "<plugin>/scripts/py" scripts/guarda.py review-save --dir "<R>" --lens failures --chunk all --round 1 --answer-file "<S>/answer-failures-all-1.txt"
```

One plain command with literal paths (no `cd`, `;`, `$R`/`$S` variables): only that form passes the guard without asking the owner.

- `{"ok":true,"lens_ran":true,"path","counts","blocking","rejected"}`: keep only counts + path + at most 25 lines; the fixers read `path` themselves.
- `{"ok":false,"usage":true,"lens_ran":null,"error"}`: the CALL is wrong (argument, folder, name already used). Fix the call; do not ask the reviewer again.
- `{"ok":false,"lens_ran":false,"error"}`: that lens did NOT run. Ask the same reviewer once; still invalid = `names.need_you`.
- `--round` = the next free number for that lens and chunk in `<R>`: a recheck, an answer asked again or asked to justify, and a resumed review each take a new one.

## Fix

- CRITICAL/HIGH with `introduced` true, grouped by file group, about 5 per executor. Executors in SEQUENCE (same worktree), each a NEW executor (medium), `tune-up:executor-sonnet`, or `tune-up:executor-opus` when a finding of its group is CRITICAL or comes from the database or security lens, the item is risky (end review: the Part has a risky item), or it is the second fix; it gets: the original order(s), the path of the findings json, its group. It commits and returns the hash, which differs from the commit before it (else interrupted: nothing to recheck). Note the commit before and after each fix.
- Recheck: only the lenses that still have an open CRITICAL/HIGH, same chunks. Model: sonnet; the lens's own model once that unit had a CRITICAL. Prompt:

```
Recheck. Diff of the fix ONLY: git diff --no-ext-diff --ignore-submodules=none <before fix>..<after fix>
PREVIOUS FINDINGS: <the open findings from the json file>
Mark each finding closed or reopened, with file:line proof. A reopened finding is listed again with the same file, title and sev and introduced:true. Report a new CRITICAL/HIGH only if the fix introduced it.
```

- A recheck finding that matches a PREVIOUS FINDING blocks, whatever its `introduced` says.
- After a fix, run `rota --part` again on `<base>..HEAD`: a lens it newly asks for reviews the whole Part now.
- Save each recheck answer. A CRITICAL/HIGH left after the second fix, or a count that did not drop: `names.need_you` and STOP.

## Pending line and done

- Written BEFORE the first dispatch of the Part (before call 1 of the Workflow), at the line start; update the items as they finish, never duplicate it ("Parte" / "desde" in Portuguese):
  `- <names.review_pending> - Part X - since <base> (items none yet)`, then `(items B1 reviewed at <commit>, B2)`.
- A base item's approval, or a resumed review with items still to run, never erases it; the end review still covers `<base>..HEAD`.
- Only the END review's approval replaces it by `review done at <commit>`, without the marker. A fix after that puts it back until its recheck is approved. Check:

```
sh "<plugin>/scripts/py" scripts/guarda.py review-pending --file "<absolute path of the LOCAL progress>" --part <X>
```

- It must be `{"pending":false}` before Step 5. `pending` true, an `error` (even with `lines` empty) or no JSON = pending: STOP and say it.
