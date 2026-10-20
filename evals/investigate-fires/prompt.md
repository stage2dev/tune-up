---
name: investigate-fires
description: A request to find the cause of a bug without changing anything fires the investigate skill.
max_turns: 10
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
tags: [smoke]
runs: 1
---
the customer's chatbot stopped answering yesterday at 3pm, find out why and tell me what you found.
