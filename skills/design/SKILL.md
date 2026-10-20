---
name: design
description: Builds the design system (DESIGN.md with tokens) and a static HTML prototype made from it. Use for "design system", "prototype", "DESIGN.md", "screen", "protótipo", "tela", "sistema de design", "identidade visual".
argument-hint: "[visual direction or references]"
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/guarda.py" info)
---

# Design system and prototype

Context: !`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/guarda.py" info`

Request: $ARGUMENTS

The JSON above is the context. Talk to the user in its `language`, honoring `reply_style`. Name the design document with `names.design` (never a literal name); read the project docs by `names.vision` and `names.prd`. If `info` failed, say so and use defaults.

Output: `docs/<names.design>` (tokens + prose) and `docs/prototype/index.html` (static, offline). Work at the git toplevel of the project. No commit, no push, no install.

## Step 0 - Preconditions

- If talk mode is on (the hook blocks code writes), the HTML cannot be written: say the exit phrases (en: "let's build", "start building"; pt-BR: "pode construir", "comece a aplicar") and wait. You may still write the `.md` first.
- Read `names.vision` / `names.prd` if they exist (audience, tone, platform). If there is no project yet, ask only what you need and still write into `docs/`.
- If `docs/<names.design>` exists, read it and update it instead of starting over.

## Step 1 - Visual direction

Ask with `AskUserQuestion`, one round:
1. Direction: offer 2 or 3 options, each described in one line of concrete traits (palette mood, type feel, density, corner style), fitted to the product and audience. Example shapes: "calm and airy: light surface, one soft accent, generous spacing"; "dense and technical: neutral greys, monospace accents, tight spacing"; "bold and playful: saturated primary, large rounded corners". Always allow "other".
2. References: ask for sites, apps or screenshots the user likes or dislikes (free text; "none" is fine). Never invent a brand.
3. Dark, light or both; the fonts must be available offline-safe (system stacks) unless the user names one.

Then propose the concrete token values in a short list (5 colors, 2 type styles, radius, 3 spacing steps) and ask for approval or changes. One round of changes at most, then decide and note it as `[ASSUMPTION]`.

## Step 2 - Write the design document

Use `${CLAUDE_PLUGIN_ROOT}/templates/project/design.md` as the shape; translate headings and text to `language`; fill every `{{placeholder}}`; delete empty sections; keep the frontmatter keys in English.

Format rules for the frontmatter (the converter reads this subset only):
- 2-space indent, `key: value`, no lists. QUOTE every hex color (an unquoted `#fff` is a comment).
- Required tokens (the prototype uses them): `name`, `description`, `colors.{primary,secondary,surface,text,error}`, `typography.body.{fontFamily,fontSize,fontWeight,lineHeight}`, `typography.heading.{fontFamily,fontSize,fontWeight}`, `rounded.md`, `spacing.{sm,md,lg}`. Add more groups or components as needed; references look like `"{colors.primary}"`.
- Contrast: `text` on `surface` and `surface` on `primary` must reach 4.5:1 (WCAG AA). Compute the ratio and adjust; state the ratios in the Colors prose.
- Prose follows the order of the template; include "Voice and tone" (do/don't table) and "Key flows" from the interview, not generic text.

## Step 3 - Generate the prototype

```
mkdir -p docs/prototype
python3 "${CLAUDE_PLUGIN_ROOT}/skills/design/scripts/tokens_to_css.py" docs/<names.design> \
  --prototype "${CLAUDE_PLUGIN_ROOT}/skills/design/templates/prototype.html" --out docs/prototype/index.html
```

(Run it with the Bash tool; the command above is not pre-approved, the user may be asked.) If it reports a missing token or broken reference, fix the design document and rerun.

Then edit `docs/prototype/index.html`:
- Replace the block marked `MAIN SCREEN` with the product's one key screen (from `names.prd`'s main flow), with made-up data. Use only existing classes and `var(--...)` tokens: no loose colors, no new fonts.
- Translate visible labels to the project language.
- Keep the component sections (buttons, fields, card, list, empty and error states).
- Rule: CSS stays inline; no CDN, no web fonts, no `<link>`, no `<script src>`, no URL of any kind, no network.

Check: `grep -c "http" docs/prototype/index.html` must print 0. Regenerating overwrites the file, so redo the main-screen edit after a token change.

## Step 4 - Approval

Tell the user to open it: `open docs/prototype/index.html` (macOS), `xdg-open ...` (Linux) or double-click it. Ask what to change; apply changes to the tokens first, then regenerate. Do not start implementing the real UI before the user approves.

## Step 5 - Finish

Short answer: direction chosen, files written (`docs/<names.design>`, `docs/prototype/index.html`), contrast ratios, open points. Next step: `/tune-up:plan` (the first plan item can build the front end from the tokens). Optional for the user: `npx @google/design.md lint docs/<names.design>` for an extra check (needs network; you do not run it).
