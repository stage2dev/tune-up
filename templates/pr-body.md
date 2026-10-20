# PR body template

Write in the user's `language` (from `info`). Fill everything; delete what does not apply, but keep "Did not run".

```markdown
## Deploy order
1. <SQL/migration, if any: file and who applies it> or "no migration"
2. Merge (owner)
3. Backend deploy: <yes/no>
4. Frontend deploy: <yes/no>
New environment variables: <list or "none">

## What changed
- <item 1, one line, with the why>
- <item 2>

## Did not run
- <CI / test / command>: <reason>
(If everything ran, write "everything ran" and list the commands with results.)

## Pre-existing on main
- <failure that already existed and is not from this PR> or "nothing found"

## How the owner tests in production
1. <observable step>
2. <expected result>

## Pending
- Migration pending: yes/no
- Left for later ({{names.later}}): <items or "nothing">
```
