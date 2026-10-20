---
name: epsilon-hooks
description: Lint after each edit.
hooks:
  PostToolUse:
    - matcher: "Edit|Write"
      hooks:
        - type: command
          command: "./lint.sh"
---
Keep the code tidy.
