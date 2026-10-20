# {{project_name}} - {{names.agents}}

Rules for AI agents working in this repo. The closest file wins in a subfolder.

## Overview
{{what_this_project_is_in_two_lines}}

## Commands
- Setup: {{command}}
- Dev: {{command}}
- Test: {{command}}
- Lint: {{command}}

## Style
{{language_and_formatting_rules}}

## Rules
- Smallest change that works. No new dependency, abstraction or file unless the task needs it.
- Code files stay at or under 450 lines. Split before growing past it; a deliberate exception needs `tune-up: allow-long <reason>` in the first 5 lines.
- Read the nearby code and match its naming and style before editing.
- Prove a change by running it; report what you observed.

## Tests
{{how_to_run_and_where_they_live}}

## Security
- Secrets stay out of git; `.env.example` holds names only.
- {{project_specific_limits}}

## Documents
Project docs in `docs/`; phase plans in `{{plans_dir}}/`.
