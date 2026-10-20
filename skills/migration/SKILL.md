---
name: migration
description: "Applies a database migration/SQL to production with a safe protocol. Use on: merged, apply the migration, where is the SQL; mergeei, pode aplicar, aplica a migration. Only on the owner's explicit request this turn."
argument-hint: "<PR, file or migration name>"
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/guarda.py" info)
---

# Migration in production

Target: $ARGUMENTS

## Context (injected)

Context: !`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/guarda.py" info`

Fields: `language`, `owner`, `reply_style`, `names{}`, `models{}`, `forbidden_subagent_models` (default `["fable"]`), `profile_path`, `plans_dir`, `setup_done`, `tools`, `plugin_source`, `catalog_path`. Write every reply and document in `language`. Never hardcode marker or document names: use the values in `names` (keys such as `need_you`, `progress`, `part_closed`). Call the user `owner`. If the JSON did not load, run the command once with Bash.

Short final reply. Read the project profile (`profile_path`): what production is, ids, database tools, type regeneration, what never to touch.

## Steps

1. **Request in this turn.** Writing to production needs the owner's request in their own words THIS turn ("go ahead and apply", "apply it"). A "yes" to another question, a vague "go", or "recommended" do not count. Without it: write `names.need_you` asking for the words, and stop.
2. **Deploy order.** Is the PR merged? (`gh pr view --json state`). The migration goes BEFORE the backend that depends on it. If the backend already shipped without the migration, warn about the risk before applying.
3. **Read the whole file.** Every statement. Look for: DROP, REVOKE, DELETE without WHERE, triggers, `SECURITY DEFINER`, backfill, long locks.
4. **Pre-checks (SELECT only on production).** Current state: columns and tables, real production policies (the repo may be stale), affected data (count), whether the migration was already applied.
5. **Backup and undo.** Before touching data: back up the affected rows and write the SQL that undoes it. Keep them in the scratchpad.
6. **Apply.** One of two routes:
   - Through the database tool in the profile, in small slices: one DELETE per call; DROP/REVOKE in a block often fails.
   - A single file `BEGIN; ...; migration-table record; COMMIT;` + a verification SELECT, tested first on a local Postgres, then copied to the clipboard for the owner to paste in the SQL editor.
7. **Verify the effect.** Query the catalog (columns, policies, functions, counts). "Success" proves nothing.
8. **Stamp.** The version stored in the migrations table may differ from the file name in the repo. If it differs, note it to align.
9. **Types.** If the profile says to regenerate types after a schema change, do it and leave it as a local change for the PR.
10. **Record.** Progress file of the phase (`names.progress`): what was applied, time, verification, undo. If the project has a Claude memory, record a short note there too.

## Rules

- Denied by the permission classifier: do not retry another way. Hand over the ready SQL and ask the owner to apply it.
- Failed midway: stop. Say what was already applied and run the state queries before any retry.
- Real customer data in production: only with a clear request and a backup done.
- Never write a secret (connection string, password) in a file, PR or memory.

## Answer

- What was applied and the proof (query + result).
- How to undo.
- Next step in the deploy order and whose it is (owner or you).
