---
type: regex
name: short-status
pattern: '^(?:[^\n]*\n){0,9}[^\n]*$'
match: contains
target: last_message
---
The status answer must be short (at most 10 lines), as the status skill requires.
