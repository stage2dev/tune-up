---
name: status-summary
description: A status request is answered in the summary format.
max_turns: 10
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Bash, Skill]
tags: [smoke]
runs: 1
---
status?
