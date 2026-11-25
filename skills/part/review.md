# Part review - detail

Every guarda call is `sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py ...`. `<S>` = the scratchpad.

## Route and call

1. `git diff --name-only --no-renames <base>..HEAD` and `git diff --no-renames <base>..HEAD > <S>/diff-part.patch`, then `rota --part --files <names> --diff-file <S>/diff-part.patch`. Answer: `{"part":true,"risk","reviewers","model":"opus","effort":"high","lines","chunks","why"}`. An error counts as risk: call all three lenses.
2. One call per reviewer of `reviewers` (never fewer), opus, high, ALL in ONE message, background. Each gets: `git diff <base>..HEAD` (or its chunk's paths), criterion C, `PITFALLS TO READ`, and the base items already reviewed with the commit of each.
3. `chunks` > 1: split by side (front, back) or by item group. Each chunk goes to EVERY reviewer of the route, with `git diff --stat <base>..HEAD` of the WHOLE Part. Add one reviewer-failures for the boundaries between chunks (for example front x back: contracts, field names, order of deploy). Labels: `front`, `back`, `boundary`; one chunk or none: `all`; a base item: `item-b1`.
4. DUPLICATION: HIGH only when the copies already diverge or must change together; otherwise MEDIUM.

## Saving an answer

The reviewer has no Write. Its final answer is the CRITICAL/HIGH list, a compact json block with ALL findings, then the Verdict line (about 25 lines). Pass the WHOLE answer on stdin (quoted heredoc):

```
sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py review-save --dir <S> --lens failures --chunk all --round 1 <<'END'
<the reviewer's answer>
END
```

Answer: `{"ok","lens_ran","path","counts","blocking","rejected"}` or `{"ok":false,"lens_ran":false,"error"}`. Keep only counts + path + at most 25 lines in your context; the fixers read `path` themselves. `--round` is 1 for the first review, +1 per recheck.

## Fix

- CRITICAL/HIGH with `introduced` true, grouped by file group, about 5 per executor. Executors in SEQUENCE (same worktree), each a NEW `tune-up:executor-opus` (opus, medium) that gets: the original order(s), the path of the findings json, its group. It commits and returns the hash. Note the commit before and after each fix.
- Recheck: only the lenses that still have an open CRITICAL/HIGH, same chunks. Prompt:

```
Recheck. Diff of the fix ONLY: git diff <before fix>..<after fix>
PREVIOUS FINDINGS: <the open findings from the json file>
Mark each finding closed or reopened, with file:line proof. Report a new CRITICAL/HIGH only if the fix introduced it.
```

- Save each recheck answer with `review-save`, `--round` +1. After the second fix, a recheck that still has CRITICAL/HIGH, or a count that did not drop: `names.need_you` and STOP.

## Pending line and done

- Pending line in progress, at the line start, written after EVERY item (update it, never duplicate):
  `- <names.review_pending> - Part X - since <commit before the first unreviewed item> (items B1, B2)` ("Parte" / "desde" in Portuguese). An approved base item leaves the list of items; `since` keeps pointing at the first unreviewed item.
- Approved: replace the line by `review done at <commit>`, without the marker. Check with `review-pending --file <progress> --part <X>` (`{"pending","lines"}`): it must be false before Step 5.
