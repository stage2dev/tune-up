# Project profile - <short name>

> Read by tune-up before plan, part, investigate, ship and migration. Keep it short and true. No secrets.
> Write this file in the project language (`language` in config.json, else the user language).

## Identity
- Product and what it does, in 1-2 lines. Old names or nicknames.
- Language of customer-facing messages. Business time zone.
- Where sessions open and where the repository lives.

## Repository and branches
- Git folder, remote, main branch.
- Code folders (front, back, others) and plans folder (`<plans_dir>/phases/NNN-kebab/`).
- Branch, commit and PR conventions (`feat/...`, `fix/...`).
- Do other sessions edit the same repo? How to avoid collisions (worktree, `git add` by name).

## Who does what
- Merge: owner / Claude.
- Deploy: who, where, in what order (SQL -> merge -> back -> front?).
- Migration: who applies, with which tool, where the files live.
- Environment variables and deploy dashboards: whose.

## Definition of done (commands)
| Layer | Command | Note |
|---|---|---|
| Lint | `<command>` | |
| Types | `<command>` | |
| Tests | `<command>` | |
| Other | `<command>` | |
- Failures already present on main: <list or "none known">.
- Does CI run? If not, how to compensate.

## Diagnostic sources
- Logs: <where, how to search, retention>.
- Traces/errors: <tool, useful filter>.
- Database: <tool, READ-ONLY, key tables>.
- Investigation skill of the module, if any: <name>.

## Production
- What production is (project ids, URLs). Ids live here, not in the plugin core.
- What to never touch: <customer data, outbound message lines, accounts>.
- Writing to production: only on the owner's request in the turn.

## Pitfalls
- <rule in 1 line - why in 1 line>

## Pilots and customers that are not guinea pigs
- <customer - why not to touch>

## Folders
- Plans: <path>. Free folders in research mode: <list>.
- Synced folders (file-sync tools): <list>; permission rule and file reversion.
